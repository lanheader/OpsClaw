"""
通用消息处理器

处理跨渠道的通用业务逻辑：
- 用户绑定验证
- 会话管理
- 特殊命令处理
- 审批流程
- Agent 调用
"""

from typing import Optional
from app.utils.logger import get_logger

from app.integrations.messaging.base_channel import (
    IncomingMessage,
    OutgoingMessage,
    ChannelContext,
    MessageType,
)
from app.integrations.messaging.base_channel import BaseChannelAdapter

# 导入各处理器
from app.integrations.messaging.handlers.user_binding_handler import UserBindingHandler
from app.integrations.messaging.handlers.session_handler import SessionHandler
from app.integrations.messaging.handlers.command_handler import CommandHandler
from app.integrations.messaging.handlers.approval_handler import ApprovalHandler
from app.integrations.messaging.handlers.agent_invoker import AgentInvoker

logger = get_logger(__name__)


class MessageProcessor:
    """
    通用消息处理器

    职责：
    1. 编排消息处理流程
    2. 协调各个业务处理器
    3. 确保流程的一致性

    流程：
    用户验证 → 会话管理 → 特殊命令 → 审批检查 → Agent 调用
    """

    def __init__(self, channel_adapter: BaseChannelAdapter):
        """
        初始化消息处理器

        Args:
            channel_adapter: 渠道适配器
        """
        self.channel = channel_adapter

        # 初始化各处理器
        self.user_binding_handler = UserBindingHandler(channel_adapter)
        self.session_handler = SessionHandler()
        self.command_handler = CommandHandler(channel_adapter, self.session_handler)
        self.approval_handler = ApprovalHandler(channel_adapter)
        self.agent_invoker = AgentInvoker(channel_adapter)

    async def process_message(self, message: IncomingMessage) -> None:
        """
        处理消息的主流程

        Args:
            message: 入站消息

        流程：
        1. 用户绑定验证
        2. 获取或创建会话
        3. 处理特殊命令
        4. 检查审批状态
        5. 调用 Agent 处理
        """
        try:
            logger.info(
                f"📨 处理消息: channel={message.channel_type}, "
                f"sender={message.sender_id}, text={message.text[:50]}..."
            )

            # 1. 用户绑定验证
            user = await self.user_binding_handler.verify_binding(
                sender_id=message.sender_id,
                channel_type=message.channel_type,
                chat_id=message.chat_id
            )

            if not user:
                # 用户未绑定或已禁用，警告消息已由 handler 发送
                return

            # 2. 获取或创建会话
            context = await self.session_handler.get_or_create_context(
                chat_id=message.chat_id,
                sender_id=message.sender_id,
                sender_name=message.sender_name,
                channel_type=message.channel_type,
                user_id=user.id
            )

            # 设置原始消息ID（用于添加表情回复）
            context.message_id = message.message_id

            # 3. 处理特殊命令
            if await self.command_handler.handle_command(message.text, context):
                return

            # 4. 检查审批状态
            if await self.approval_handler.handle_pending_approval(context, message.text):
                return

            # 5. 调用 Agent 处理
            await self.agent_invoker.invoke_agent(context, message.text)

        except Exception as e:
            logger.exception(f"❌ 消息处理失败: {e}")
            await self._send_error_message(message, str(e))

    # ========== 辅助方法 ==========

    async def _send_error_message(
        self,
        message: IncomingMessage,
        error: str
    ) -> None:
        """发送错误消息"""
        error_msg = f"❌ 处理消息时出错: {error}\n\n请稍后重试或联系管理员"

        outgoing = OutgoingMessage(
            chat_id=message.chat_id,
            message_type=MessageType.TEXT,
            content={"text": error_msg}
        )

        try:
            await self.channel.send_message(outgoing)
        except Exception as e:
            logger.error(f"发送错误消息失败: {e}")
