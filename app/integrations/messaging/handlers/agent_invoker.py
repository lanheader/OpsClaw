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
from app.integrations.feishu.message import build_formatted_reply_card
from app.integrations.feishu.message_formatter import clean_xml_tags
from app.models.database import SessionLocal
from app.services.chat_service import save_feishu_message
from app.models.chat_message import MessageRole

logger = get_logger(__name__)

AGENT_TIMEOUT = 300  # 5 分钟，与 chat.py 一致
MAX_RETRY = 0        # 不重试，直接返回结果

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
                include_summary=True,
                include_mem0=True,
                max_tokens=4500,
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
        event_count = 0  # 🔍 诊断：统计事件数量

        try:
            done = False
            for attempt in range(MAX_RETRY + 1):
                if done:
                    break

                start_time = time.time()
                logger.info(f"🔍 开始流式处理: attempt={attempt}, MAX_RETRY={MAX_RETRY}")

                # LangGraph 默认使用 stream_mode="values"，返回每个节点执行后的完整 state
                # 最后一个事件就是最终的 state
                last_event = None
                async for event in agent.astream(input_state, config=config):
                    event_count += 1
                    last_event = event  # 保存最后一个事件

                    # 🔍 详细诊断：打印事件的完整结构
                    if isinstance(event, dict):
                        event_keys = list(event.keys())
                        logger.info(
                            f"🔍 收到事件 #{event_count}: keys={event_keys}"
                        )
                    else:
                        logger.info(f"🔍 收到事件 #{event_count}: 不是字典类型，type={type(event)}")

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

                # 流式处理完成后，从所有事件中找到包含有效 state 的事件
                # 注意：某些中间件节点可能返回 None，我们需要找到包含 messages 的 state
                final_state = {}
                if last_event and isinstance(last_event, dict):
                    # 🔍 诊断：打印最后一个事件的完整内容
                    logger.info(f"🔍 最后一个事件的完整内容: {str(last_event)[:500]}")

                    # 尝试从最后一个事件中提取 state
                    last_state = list(last_event.values())[0] if last_event else None
                    if last_state and isinstance(last_state, dict) and "messages" in last_state:
                        final_state = last_state
                        logger.info(f"🔍 从最后一个事件中找到有效 state")
                    else:
                        # 如果最后一个事件的 state 无效（None 或空字典），
                        # 我们需要使用 ainvoke 来获取最终的 state
                        logger.warning(f"⚠️ 最后一个事件的 state 无效，使用 ainvoke 获取最终 state")
                        try:
                            final_result = await agent.ainvoke(input_state, config=config)
                            if isinstance(final_result, dict):
                                final_state = final_result
                                logger.info(f"✅ 通过 ainvoke 获取到最终 state: keys={list(final_state.keys())}")
                        except Exception as e:
                            logger.error(f"❌ ainvoke 失败: {e}")

                    # 🔍 诊断：打印提取的 state
                    logger.info(f"🔍 提取的 final_state 类型: {type(final_state)}, keys={list(final_state.keys()) if isinstance(final_state, dict) else 'not-dict'}")

                    final_state = ensure_final_report_in_state(final_state)
                    final_report = (
                        final_state.get("formatted_response", "") or
                        final_state.get("final_report", "")
                    )

                    # 🔍 诊断日志：记录最终事件的详细信息
                    logger.info(
                        f"🔍 处理最后一个事件（工作流完成）: "
                        f"final_report={'有内容' if final_report else '空'}, "
                        f"长度={len(final_report) if final_report else 0}, "
                        f"attempt={attempt}, "
                        f"state_keys={list(final_state.keys())}"
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
                        continue  # 继续下一次 attempt

                    # 质量合格（或已是最后一次），发送回复
                    if final_report:
                        content_hash = hash(final_report)
                        if content_hash not in all_reply_hashes:
                            try:
                                await self._send_reply(context.chat_id, final_report)
                                self._save_to_db(context.session_id, MessageRole.ASSISTANT, final_report)
                                replies.append(final_report)
                                all_reply_hashes.append(content_hash)
                                logger.info(f"✅ 已添加回复到 replies 列表: 长度={len(final_report)}")
                            except Exception as send_err:
                                logger.error(f"❌ 发送回复失败，跳过保存: {send_err}")
                        else:
                            logger.warning(f"⚠️ 回复内容重复，已跳过: hash={content_hash}")
                    else:
                        logger.warning(f"⚠️ final_report 为空，未添加到 replies")
                    done = True
                    break

                # 注意：LangGraph v1 格式不支持 interrupt/error 事件
                # 这些事件在 v1 中通过其他机制处理（如 interrupt_on 配置）

            # 5. 空回复兜底
            if not replies:
                logger.warning(
                    f"⚠️ 所有尝试均未产生有效回复: "
                    f"session={context.session_id}, "
                    f"event_count={event_count}, "
                    f"done={done}, "
                    f"all_reply_hashes={all_reply_hashes}"
                )
                fallback = (
                    "⚠️ 本次未能生成回复，可能原因：\n"
                    "- 对话上下文过长，模型处理超限\n"
                    "- 模型暂时无响应\n\n"
                    "建议：发送 /new 开启新会话后重试。"
                )
                try:
                    await self._send_reply(context.chat_id, fallback)
                    self._save_to_db(context.session_id, MessageRole.ASSISTANT, fallback)
                except Exception as send_err:
                    logger.error(f"❌ 发送兜底回复失败，跳过保存: {send_err}")

            logger.info(f"✅ Agent 调用完成: session={context.session_id}, replies={len(replies)}")

            # 6. 自动学习（对齐 chat.py）
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

    def _save_to_db(self, session_id: Optional[str], role: MessageRole, content: str) -> None:
        """保存消息到数据库"""
        if not session_id:
            return
        db = SessionLocal()
        try:
            save_feishu_message(db, session_id, role, content)
            logger.info(f"✅ 已保存消息到数据库: session={session_id}, role={role.value}")
        except Exception as e:
            logger.error(f"❌ 保存消息到数据库失败: {e}")
        finally:
            db.close()

    async def _send_reply(self, chat_id: str, content: str) -> None:
        """发送回复消息（卡片格式，支持 Markdown 渲染）"""
        cleaned = clean_xml_tags(content)
        card = build_formatted_reply_card(content=cleaned)
        outgoing = OutgoingMessage(
            chat_id=chat_id,
            message_type=MessageType.CARD,
            content=card,
        )
        await self.channel.send_message(outgoing)

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
