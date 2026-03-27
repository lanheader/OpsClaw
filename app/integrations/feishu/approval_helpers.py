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

        # 获取线程配置
        from app.deepagents.main_agent import get_thread_config
        from langchain_core.messages import HumanMessage
        config = get_thread_config(session_id)

        # 根据决策构建恢复消息
        if decision == "approved":
            logger.info(f"✅ 用户同意，准备继续执行")
            # 用户同意，发送一个确认消息来继续执行
            resume_message = HumanMessage(content="[APPROVAL_GRANTED] 用户已批准执行操作")
        else:
            logger.info(f"❌ 用户拒绝，准备中止执行")
            # 用户拒绝，发送一个拒绝消息
            resume_message = HumanMessage(content="[APPROVAL_REJECTED] 用户已拒绝执行操作")

        # 继续执行工作流
        all_replies = []
        event_count = 0
        logger.info(f"🔄 开始从中断点恢复工作流: session_id={session_id}")

        try:
            # 使用 ainvoke 继续执行
            result = await agent.ainvoke(
                {"messages": [resume_message]},
                config=config
            )

            logger.info(f"🔍 ainvoke 返回结果: keys={list(result.keys()) if isinstance(result, dict) else type(result)}")

            # 从结果中提取回复
            if isinstance(result, dict):
                response = result.get("formatted_response", "") or \
                          result.get("final_report", "") or \
                          result.get("response", "")

                # 如果没有找到，尝试从 messages 中提取最后一条 AI 消息
                if not response and "messages" in result:
                    messages = result["messages"]
                    if messages and len(messages) > 0:
                        last_message = messages[-1]
                        if hasattr(last_message, 'content'):
                            response = last_message.content

                if response:
                    logger.info(f"✅ 提取到回复: {response[:100]}...")
                    all_replies.append(response)
                else:
                    logger.warning(f"⚠️ 结果中没有找到回复内容")

            logger.info(f"🔍 工作流恢复完成: 提取到 {len(all_replies)} 条回复")
        except Exception as stream_exc:
            logger.error(f"❌ ainvoke 执行失败: {stream_exc}", exc_info=True)

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
