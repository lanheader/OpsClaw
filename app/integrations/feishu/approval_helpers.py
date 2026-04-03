"""
飞书审批辅助函数

这些函数被新架构和旧代码共享，用于处理审批流程。

根据 DeepAgents 文档，正确的审批恢复流程：
1. 使用 interrupt_on 配置需要审批的工具
2. 当工具被中断时，使用 Command(resume=...) 恢复执行
3. resume 参数格式（HITLResponse）:
   - 批准: {"decisions": [{"type": "approve"}]}
   - 拒绝: {"decisions": [{"type": "reject", "message": "用户拒绝原因"}]}
"""

from typing import Dict, Any, Literal

from langgraph.types import Command

from app.utils.logger import get_logger
from app.deepagents.factory import create_agent_for_session
from app.deepagents.main_agent import get_thread_config
from app.services.session_state_manager import SessionStateManager
from app.integrations.messaging.base_channel import OutgoingMessage, MessageType
from app.integrations.feishu.message import build_formatted_reply_card
from app.integrations.feishu.message_formatter import clean_xml_tags
from app.utils.llm_helper import ensure_final_report_in_state, extract_final_report_from_messages

logger = get_logger(__name__)


async def _send_card_message(channel_adapter, chat_id: str, content: str) -> None:  # type: ignore[no-untyped-def]
    """发送卡片消息（支持 Markdown 渲染）"""
    cleaned = clean_xml_tags(content)
    card = build_formatted_reply_card(content=cleaned)
    outgoing = OutgoingMessage(
        chat_id=chat_id,
        message_type=MessageType.CARD,
        content=card,
    )
    await channel_adapter.send_message(outgoing)


def _build_resume_value(decision: str, message: str = "", num_decisions: int = 1) -> Dict[str, Any]:
    """
    构建 DeepAgents HITLResponse 格式的恢复值

    Args:
        decision: 决策类型 (approved/rejected)
        message: 拒绝原因（可选）
        num_decisions: 需要的决策数量（对应挂起的工具调用数量）

    Returns:
        HITLResponse 格式的字典
    """
    if decision == "approved":
        # 为每个挂起的工具调用创建一个批准决策
        decisions = [{"type": "approve"} for _ in range(num_decisions)]
        return {"decisions": decisions}
    else:
        # 为每个挂起的工具调用创建一个拒绝决策
        decisions = [
            {
                "type": "reject",
                "message": message or "用户拒绝了此操作"
            }
            for _ in range(num_decisions)
        ]
        return {"decisions": decisions}


def _extract_response_from_state(state: Dict[str, Any]) -> str:
    """
    从 state 中提取回复内容

    Args:
        state: 工作流状态

    Returns:
        提取的回复字符串
    """
    if not state or not isinstance(state, dict):
        return ""

    # 确保 final_report 存在
    state = ensure_final_report_in_state(state)

    # 尝试多种字段名（按优先级）
    response = (
        state.get("formatted_response", "") or
        state.get("final_report", "") or
        state.get("final_answer", "") or  # DeepAgents 可能使用这个字段
        state.get("response", "") or
        state.get("answer", "")
    )

    if response:
        return response  # type: ignore[no-any-return]

    # 如果上述字段都为空，尝试从 messages 中提取
    messages = state.get("messages", [])
    if messages:
        return extract_final_report_from_messages(messages)

    return ""


async def handle_approval_response(  # type: ignore[no-untyped-def]
    session_id: str,
    decision: str,
    chat_id: str,
    user_response: str,
    channel_adapter=None
) -> Literal["completed", "interrupted", "not_awaiting"]:
    """
    处理批准响应，恢复工作流。

    Args:
        session_id: 会话ID
        decision: 决策（approved/rejected）
        chat_id: 会话ID
        user_response: 用户响应
        channel_adapter: 渠道适配器（可选）

    Returns:
        执行状态
    """

    logger.info(f"开始处理批准响应: session_id={session_id}, decision={decision}")

    # 检查是否在等待批准
    approval_data = SessionStateManager.check_awaiting_approval(session_id)
    if not approval_data:
        logger.warning(f"⚠️ 会话 {session_id} 不在等待批准状态")
        return "not_awaiting"

    try:
        # 创建 Agent
        agent = await create_agent_for_session(
            enable_approval=True,
        )

        # 获取线程配置
        config = get_thread_config(session_id)

        # 根据决策构建恢复命令（使用正确的 HITLResponse 格式）
        # 获取需要决策的工具调用数量
        action_requests = approval_data.get('action_requests', [])
        num_decisions = len(action_requests) if action_requests else 1
        resume_value = _build_resume_value(decision, user_response, num_decisions)

        if decision == "approved":
            logger.info(f"✅ 用户同意，准备继续执行: num_decisions={num_decisions}, resume_value={resume_value}")
        else:
            logger.info(f"❌ 用户拒绝，准备中止执行: num_decisions={num_decisions}, resume_value={resume_value}")

        all_replies = []
        event_count = 0
        last_state = None
        new_interrupt_detected = False
        collected_messages = []  # 收集所有消息，用于最终回复

        try:
            # 使用 astream + Command 恢复执行
            async for event in agent.astream(
                Command(resume=resume_value),
                config=config
            ):
                event_count += 1

                # 🔍 诊断：打印事件结构
                if isinstance(event, dict):
                    event_keys = list(event.keys())
                    logger.info(f"🔍 收到事件 #{event_count}: keys={event_keys}")

                    # 检查是否又触发了新的审批中断
                    if "__interrupt__" in event:
                        logger.info("🔒 检测到新的审批中断事件")
                        new_interrupt_detected = True
                        # 提取新的审批信息并保存
                        interrupt_data = event["__interrupt__"]
                        if isinstance(interrupt_data, tuple) and len(interrupt_data) > 0:
                            interrupt_obj = interrupt_data[0]
                            if hasattr(interrupt_obj, 'value'):
                                approval_info = interrupt_obj.value
                                SessionStateManager.set_awaiting_approval(
                                    session_id,
                                    approval_data=approval_info
                                )
                                logger.info(f"📋 保存新的审批信息")
                        # 继续处理事件，不要立即返回！

                    # 提取最后一个有效状态（用于获取最终回复）
                    # LangGraph 事件格式: {node_name: state_dict}
                    for key, value in event.items():
                        if key == "__interrupt__":
                            continue
                        if isinstance(value, dict):
                            # 打印状态的键，帮助调试
                            state_keys = list(value.keys()) if isinstance(value, dict) else []
                            logger.info(f"🔍 节点 '{key}' 状态键: {state_keys}")

                            if "messages" in value:
                                last_state = value
                                msg_count = len(value.get("messages", []))
                                logger.info(f"🔍 更新 last_state from node: {key}, messages 数量: {msg_count}")

                                # 收集新增的消息（用于最终提取回复）
                                messages = value.get("messages", [])
                                if messages:
                                    collected_messages.extend(messages)

            logger.info(f"🔍 工作流恢复完成: 收到 {event_count} 个事件, 收集 {len(collected_messages)} 条消息")

            # 从最后一个状态提取回复
            if last_state:
                # 🔍 调试：打印 last_state 的所有键
                logger.info(f"🔍 last_state 键: {list(last_state.keys())}")

                # 优先从 collected_messages 提取（更完整）
                if collected_messages:
                    logger.info(f"🔍 从 collected_messages 提取回复 ({len(collected_messages)} 条)")
                    from app.utils.llm_helper import extract_final_report_from_messages
                    response = extract_final_report_from_messages(collected_messages)
                    if response:
                        logger.info(f"✅ 从 collected_messages 提取到回复 (长度: {len(response)})")
                        logger.debug(f"📝 回复预览: {response[:200]}...")
                        all_replies.append(response)
                    else:
                        # 回退到从 last_state 提取
                        response = _extract_response_from_state(last_state)
                        if response:
                            logger.info(f"✅ 从 last_state 提取到回复 (长度: {len(response)})")
                            all_replies.append(response)
                else:
                    # 没有 collected_messages，直接从 last_state 提取
                    response = _extract_response_from_state(last_state)
                    if response:
                        logger.info(f"✅ 提取到回复 (长度: {len(response)})")
                        logger.debug(f"📝 回复预览: {response[:200]}...")
                        all_replies.append(response)
                    else:
                        logger.warning("⚠️ 未能从 last_state 提取到回复")
                        # 尝试从 messages 中提取
                        messages = last_state.get("messages", [])
                        if messages:
                            logger.info(f"🔍 尝试从 messages 提取回复 ({len(messages)} 条消息)")
                            from app.utils.llm_helper import extract_final_report_from_messages
                            response = extract_final_report_from_messages(messages)
                            if response:
                                logger.info(f"✅ 从 messages 提取到回复 (长度: {len(response)})")
                                all_replies.append(response)

            # 如果检测到新的中断，返回 interrupted 状态
            if new_interrupt_detected:
                logger.info("🔒 工作流有新的审批请求，返回 interrupted 状态")
                return "interrupted"

        except Exception as stream_exc:
            logger.error(f"❌ astream 执行失败: {stream_exc}", exc_info=True)
            # 尝试使用 ainvoke 作为备选方案
            try:
                logger.info("🔄 尝试使用 ainvoke 作为备选方案...")
                result = await agent.ainvoke(
                    Command(resume=resume_value),
                    config=config
                )

                if isinstance(result, dict):
                    response = _extract_response_from_state(result)
                    if response:
                        all_replies.append(response)
                        logger.info(f"✅ 备选方案成功: {response[:100]}...")

            except Exception as invoke_exc:
                logger.error(f"❌ ainvoke 备选方案也失败: {invoke_exc}", exc_info=True)

        # 发送回复
        if channel_adapter and all_replies:
            for reply in all_replies:
                await _send_card_message(channel_adapter, chat_id, reply)

        # 清除审批状态
        SessionStateManager.reset_to_normal(session_id)
        logger.info(f"✅ 批准响应处理完成: session_id={session_id}, decision={decision}")
        return "completed"

    except Exception as exc:
        logger.error(f"❌ 处理批准响应失败: {exc}", exc_info=True)
        # 发送错误消息
        if channel_adapter:
            error_msg = f"❌ 处理批准响应失败: {str(exc)}"
            try:
                await _send_card_message(channel_adapter, chat_id, error_msg)
            except Exception as send_err:
                logger.error(f"发送错误消息失败: {send_err}")

        raise
