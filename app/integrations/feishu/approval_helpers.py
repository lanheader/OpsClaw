"""
飞书审批辅助函数

这些函数被新架构和旧代码共享，用于处理审批流程。
"""

from typing import Dict, Any, Literal

from app.utils.logger import get_logger
from app.deepagents.factory import create_agent_for_session
from app.services.session_state_manager import SessionStateManager
from app.integrations.messaging.base_channel import OutgoingMessage, MessageType

logger = get_logger(__name__)


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

        # 构建恢复状态
        resume_state: Dict[str, Any] = {
            "session_id": session_id,
            "workflow_status": "running",
            "approval_status": decision,
            "approval_decision": decision,
            "is_approval_response": True,
            "waiting_for_approval": False,
            "approval_required": False,
        }

        # 执行工作流
        all_replies = []
        async for event in agent.astream(resume_state):
            # 处理事件并收集回复
            if "__end__" in event:
                final_state = event.get("__end__", {})
                response = final_state.get("formatted_response", "") or \
                          final_state.get("final_report", "") or \
                          final_state.get("response", "")

                if response:
                    all_replies.append(response)

        # 发送回复
        if channel_adapter and all_replies:
            for reply in all_replies:
                outgoing = OutgoingMessage(
                    chat_id=chat_id,
                    message_type=MessageType.TEXT,
                    content={"text": reply}
                )
                await channel_adapter.send_message(outgoing)

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
