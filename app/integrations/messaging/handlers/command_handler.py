"""
特殊命令处理器

职责：
- 处理 /help, /new, /end 等特殊命令
"""

from typing import Optional
from app.utils.logger import get_logger

from app.integrations.messaging.base_channel import ChannelContext, MessageType, OutgoingMessage

logger = get_logger(__name__)


class CommandHandler:
    """特殊命令处理器"""

    def __init__(self, channel_adapter, session_handler):
        """
        初始化命令处理器

        Args:
            channel_adapter: 渠道适配器
            session_handler: 会话处理器
        """
        self.channel = channel_adapter
        self.session_handler = session_handler

    async def handle_command(
        self,
        text: str,
        context: ChannelContext
    ) -> bool:
        """
        处理特殊命令

        Args:
            text: 命令文本
            context: 渠道上下文

        Returns:
            True: 是特殊命令并已处理
            False: 不是特殊命令
        """
        text_lower = text.lower().strip()

        # 帮助命令
        if text_lower in ("/help", "帮助", "help"):
            await self._send_help_message(context)
            return True

        # 新会话
        if text_lower in ("/new", "新会话", "new"):
            await self._handle_new_session(context)
            return True

        # 结束会话
        if text_lower in ("/end", "结束", "end"):
            await self._handle_end_session(context)
            return True

        # 状态查询
        if text_lower in ("/status", "状态", "status"):
            await self._send_status_message(context)
            return True

        return False

    async def _send_help_message(self, context: ChannelContext) -> None:
        """发送帮助消息"""
        help_text = """🤖 运维助手命令说明

💬 常规对话：直接输入问题，我会帮您查询集群状态、诊断问题等

🔧 特殊命令：
• /help 或 帮助 - 显示此帮助信息
• /new 或 新会话 - 开始新的对话会话
• /end 或 结束 - 结束当前会话
• /status 或 状态 - 查询当前会话状态

💡 提示：您可以询问关于 Kubernetes 集群、Prometheus 监控、日志查询等问题"""

        outgoing = OutgoingMessage(
            chat_id=context.chat_id,
            message_type=MessageType.TEXT,
            content={"text": help_text}
        )

        await self.channel.send_message(outgoing)

    async def _handle_new_session(self, context: ChannelContext) -> None:
        """处理新会话命令"""
        try:
            # 创建新会话
            new_context = await self.session_handler.create_new_session(
                chat_id=context.chat_id,
                sender_id=context.sender_id,
                sender_name=context.metadata.get("sender_name"),
                channel_type=context.channel_type,
                user_id=context.user_id
            )

            message = f"✅ 已创建新会话\n\n会话ID: `{new_context.session_id}`"

            outgoing = OutgoingMessage(
                chat_id=context.chat_id,
                message_type=MessageType.TEXT,
                content={"text": message}
            )

            await self.channel.send_message(outgoing)

        except Exception as e:
            logger.exception(f"❌ 创建新会话失败: {e}")
            await self._send_error_message(context.chat_id, "创建新会话失败")

    async def _handle_end_session(self, context: ChannelContext) -> None:
        """处理结束会话命令"""
        try:
            success = await self.session_handler.end_session(context)

            if success:
                message = "✅ 会话已结束\n\n您可以发送消息开始新会话"
            else:
                message = "⚠️ 未找到活跃会话"

            outgoing = OutgoingMessage(
                chat_id=context.chat_id,
                message_type=MessageType.TEXT,
                content={"text": message}
            )

            await self.channel.send_message(outgoing)

        except Exception as e:
            logger.exception(f"❌ 结束会话失败: {e}")
            await self._send_error_message(context.chat_id, "结束会话失败")

    async def _send_status_message(self, context: ChannelContext) -> None:
        """发送状态消息"""
        status_text = f"""📊 当前会话状态

• 会话ID: `{context.session_id}`
• 渠道类型: {context.channel_type}
• 用户ID: {context.sender_id}
• 用户权限: {len(context.user_permissions)} 个

💡 提示：使用 /new 创建新会话，/end 结束当前会话"""

        outgoing = OutgoingMessage(
            chat_id=context.chat_id,
            message_type=MessageType.TEXT,
            content={"text": status_text}
        )

        await self.channel.send_message(outgoing)

    async def _send_error_message(self, chat_id: str, error_msg: str) -> None:
        """发送错误消息"""
        message = f"❌ {error_msg}\n\n请稍后重试或联系管理员"

        outgoing = OutgoingMessage(
            chat_id=chat_id,
            message_type=MessageType.TEXT,
            content={"text": message}
        )

        try:
            await self.channel.send_message(outgoing)
        except Exception as e:
            logger.error(f"发送错误消息失败: {e}")
