"""
Agent 调用器

职责：
- 调用 AI Agent 处理用户消息
- 流式处理工作流事件
- 发送 AI 回复
"""

import time
from typing import List, Dict, Any, Optional

from langchain_core.messages import AIMessage, HumanMessage

from app.utils.logger import get_logger
from app.deepagents.factory import create_agent_for_session
from app.deepagents.main_agent import get_thread_config
from app.utils.llm_helper import ensure_final_report_in_state
from app.memory.memory_manager import get_memory_manager
from app.integrations.messaging.base_channel import ChannelContext, MessageType, OutgoingMessage

logger = get_logger(__name__)

AGENT_TIMEOUT = 300  # 5 分钟，与 chat.py 一致
MAX_RETRY = 1        # 质量不足时最多重试 1 次

_FAILURE_MARKERS = ["工具调用失败", "执行失败", "无法完成", "❌ 任务失败"]


class AgentInvoker:
    """Agent 调用器"""

    def __init__(self, channel_adapter):
        self.channel = channel_adapter

    async def invoke_agent(self, context: ChannelContext, text: str) -> List[str]:
        """调用 Agent 并返回回复列表"""
        logger.info(f"🤖 调用 Agent: session={context.session_id}, text={text[:50]}...")

        # 1. 获取 Agent（FinalReportEnrichedAgent 包装）
        agent = await create_agent_for_session(
            session_id=context.session_id,
            enable_approval=True,
            user_permissions=context.user_permissions,
        )

        # 2. 记忆注入（对齐 chat.py）
        memory_manager = None
        enhanced_text = text
        try:
            memory_manager = get_memory_manager(user_id=str(context.user_id))
            context_str = await memory_manager.build_context(
                user_query=text,
                session_id=context.session_id,
                include_incidents=True,
                include_knowledge=True,
                include_session=True,
                include_mem0=True,
            )
            if context_str:
                enhanced_text = (
                    f"{text}\n\n---\n**参考资料**（来自历史对话和知识库）：\n{context_str}\n---"
                )
                logger.info(f"🧠 记忆已注入: {len(context_str)} 字符")
        except Exception as e:
            logger.warning(f"⚠️ 记忆检索失败，使用原始输入: {e}")

        # 3. 构建输入状态 & 线程配置
        input_state = {"messages": [HumanMessage(content=enhanced_text)]}
        config = get_thread_config(context.session_id)

        # 4. 流式处理（带重试）
        replies: List[str] = []
        all_reply_hashes: List[int] = []

        try:
            done = False
            for attempt in range(MAX_RETRY + 1):
                if done:
                    break

                start_time = time.time()

                async for event in agent.astream(input_state, config=config):
                    # 超时检查
                    elapsed = time.time() - start_time
                    if elapsed > AGENT_TIMEOUT:
                        logger.error(
                            f"⏰ 消息处理超时: session={context.session_id}, elapsed={elapsed:.2f}s"
                        )
                        await self._send_error_message(
                            context.chat_id, f"处理超时（{elapsed:.0f}s），请稍后重试"
                        )
                        return []

                    event_type = event.get("type")

                    if event_type == "complete":
                        final_state = ensure_final_report_in_state(event.get("state", {}))
                        final_report = (
                            final_state.get("formatted_response", "") or
                            final_state.get("final_report", "")
                        )

                        # 质量检查：不合格且还有重试机会
                        if attempt < MAX_RETRY and self._is_poor_response(final_report):
                            logger.warning(
                                f"⚠️ 回复质量不足，触发重试 (attempt={attempt}): "
                                f"report={repr(final_report[:60])}"
                            )
                            input_state = {
                                "messages": [
                                    HumanMessage(content=text),
                                    AIMessage(content=final_report or "（无回复）"),
                                    HumanMessage(content=self._build_retry_prompt(text, final_report)),
                                ]
                            }
                            break  # 跳出内层 for，进入下一次 attempt

                        # 质量合格（或已是最后一次），发送回复
                        if final_report:
                            content_hash = hash(final_report)
                            if content_hash not in all_reply_hashes:
                                await self._send_reply(context.chat_id, final_report)
                                replies.append(final_report)
                                all_reply_hashes.append(content_hash)
                        done = True
                        break

                    elif event_type == "interrupt":
                        interrupt_data = event.get("data", {})
                        approval_message = interrupt_data.get("message", "需要您的批准才能继续执行")
                        await self._send_reply(
                            context.chat_id, f"⏸️ 需要您的批准：\n\n{approval_message}"
                        )
                        replies.append(approval_message)
                        all_reply_hashes.append(hash(approval_message))
                        logger.info(f"⏸️ 工作流暂停等待审批: session={context.session_id}")
                        done = True
                        break

                    elif event_type == "node":
                        logger.info(f"📍 节点执行: {event.get('node', '')}")

                    elif event_type == "error":
                        error_msg = event.get("error", "未知错误")
                        logger.error(f"❌ 工作流执行失败: {error_msg}")
                        await self._send_error_message(context.chat_id, error_msg)
                        done = True
                        break

            # 5. 空回复兜底
            if not replies:
                fallback = (
                    "⚠️ 本次未能生成回复，可能原因：\n"
                    "- 对话上下文过长，模型处理超限\n"
                    "- 模型暂时无响应\n\n"
                    "建议：发送 /new 开启新会话后重试。"
                )
                await self._send_reply(context.chat_id, fallback)
                logger.warning(f"⚠️ 所有尝试均未产生有效回复: session={context.session_id}")

            logger.info(f"✅ Agent 调用完成: session={context.session_id}, replies={len(replies)}")

            # 6. 添加 THUMBSUP 表情
            if replies and context.message_id:
                try:
                    await self.channel.add_reaction(context.message_id, "THUMBSUP")
                    logger.debug(f"已添加 OK 表情回复: message_id={context.message_id}")
                except Exception as e:
                    logger.debug(f"添加表情回复失败: {e}")

            # 7. 自动学习（对齐 chat.py）
            if replies and memory_manager:
                try:
                    await memory_manager.auto_learn_from_result(
                        user_query=text,
                        result={"messages": [{"content": replies[-1]}]},
                        session_id=context.session_id,
                        messages=[
                            {"role": "user", "content": text},
                            {"role": "assistant", "content": replies[-1]},
                        ],
                    )
                    logger.info(f"🧠 自动学习完成: session={context.session_id}")
                except Exception as e:
                    logger.warning(f"⚠️ 自动学习失败: {e}")

            return replies

        except Exception as e:
            logger.exception(f"❌ Agent 调用失败: {e}")
            await self._send_error_message(context.chat_id, str(e))
            return []

    def _is_poor_response(self, final_report: Optional[str]) -> bool:
        """判断回复质量是否不足，触发重试"""
        if not final_report or len(final_report.strip()) < 20:
            return True
        if any(marker in final_report for marker in _FAILURE_MARKERS):
            return True
        return False

    def _build_retry_prompt(self, original_text: str, poor_response: Optional[str]) -> str:
        """构造重试 prompt"""
        if not poor_response or len(poor_response.strip()) < 20:
            return f"你没有给出有效回复，请重新回答：{original_text}"
        return f"你的回复不够完整，请重新分析并给出更详细的回答：{original_text}"

    async def _send_reply(self, chat_id: str, content: str) -> None:
        """发送回复消息"""
        try:
            outgoing = OutgoingMessage(
                chat_id=chat_id,
                message_type=MessageType.TEXT,
                content={"text": content},
            )
            await self.channel.send_message(outgoing)
        except Exception as e:
            logger.error(f"发送回复失败: {e}")

    async def _send_error_message(self, chat_id: str, error_msg: str) -> None:
        """发送错误消息"""
        message = f"❌ 处理请求时出错\n\n{error_msg}\n\n请稍后重试或联系管理员"
        outgoing = OutgoingMessage(
            chat_id=chat_id,
            message_type=MessageType.TEXT,
            content={"text": message},
        )
        try:
            await self.channel.send_message(outgoing)
        except Exception as e:
            logger.error(f"发送错误消息失败: {e}")
