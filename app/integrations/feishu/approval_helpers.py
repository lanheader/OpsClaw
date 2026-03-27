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
from app.services.session_state_manager import SessionStateManager
from app.integrations.messaging.base_channel import OutgoingMessage, MessageType

logger = get_logger(__name__)


def _build_resume_value(decision: str, message: str = "") -> Dict[str, Any]:
    """
    构建 DeepAgents HITLResponse 格式的恢复值

    Args:
        decision: 决策类型 (approved/rejected)
        message: 拒绝原因（可选）

    Returns:
        HITLResponse 格式的字典
    """
    if decision == "approved":
        return {
            "decisions": [
                {"type": "approve"}
            ]
        }
    else:
        return {
            "decisions": [
                {
                    "type": "reject",
                    "message": message or "用户拒绝了此操作"
                }
            ]
        }


async def handle_approval_response(
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
            session_id=session_id,
            enable_approval=True,
            enable_security=True,
        )

        # 获取线程配置
        from app.deepagents.main_agent import get_thread_config
        config = get_thread_config(session_id)

        # 根据决策构建恢复命令（使用正确的 HITLResponse 格式）
        resume_value = _build_resume_value(decision, user_response)

        if decision == "approved":
            logger.info(f"✅ 用户同意，准备继续执行: resume_value={resume_value}")
        else:
            logger.info(f"❌ 用户拒绝，准备中止执行: resume_value={resume_value}")

        all_replies = []
        event_count = 0

        try:
            # 使用 astream + Command 恢复执行
            async for event in agent.astream(
                Command(resume=resume_value),
                config=config
            ):
                event_count += 1
                logger.debug(f"🔍 收到事件 #{event_count}: keys={list(event.keys()) if isinstance(event, dict) else type(event)}")

                # 处理事件并收集回复
                if isinstance(event, dict):
                    # 检查是否是最终状态
                    if "__end__" in event:
                        final_state = event.get("__end__", {})
                        response = (
                            final_state.get("formatted_response", "") or
                            final_state.get("final_report", "") or
                            final_state.get("response", "")
                        )

                        if response:
                            logger.info(f"✅ 提取到回复: {response[:100]}...")
                            all_replies.append(response)

                    # 检查是否又触发了新的审批中断
                    elif "__interrupt__" in event:
                        logger.info("🔒 检测到新的审批中断事件")
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
                                # 返回 interrupted 状态，表示有新的审批请求
                                return "interrupted"

            logger.info(f"🔍 工作流恢复完成: 收到 {event_count} 个事件，提取到 {len(all_replies)} 条回复")

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
                    response = (
                        result.get("formatted_response", "") or
                        result.get("final_report", "") or
                        result.get("response", "")
                    )
                    if response:
                        all_replies.append(response)
                        logger.info(f"✅ 备选方案成功: {response[:100]}...")

            except Exception as invoke_exc:
                logger.error(f"❌ ainvoke 备选方案也失败: {invoke_exc}", exc_info=True)

        # 发送回复
        if channel_adapter and all_replies:
            for reply in all_replies:
                outgoing = OutgoingMessage(
                    chat_id=chat_id,
                    message_type=MessageType.TEXT,
                    content={"text": reply}
                )
                await channel_adapter.send_message(outgoing)

        # 清除审批状态
        SessionStateManager.reset_to_normal(session_id)
        logger.info(f"✅ 批准响应处理完成: session_id={session_id}, decision={decision}")
        return "completed"

    except Exception as exc:
        logger.error(f"❌ 处理批准响应失败: {exc}", exc_info=True)
        # 发送错误消息
        if channel_adapter:
            error_msg = f"❌ 处理批准响应失败: {str(exc)}"
            outgoing = OutgoingMessage(
                chat_id=chat_id,
                message_type=MessageType.TEXT,
                content={"text": error_msg}
            )
            await channel_adapter.send_message(outgoing)

        raise
