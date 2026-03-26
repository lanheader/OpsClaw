"""
用户绑定验证处理器

职责：
- 验证用户是否已绑定系统账号
- 发送未绑定警告
"""

from typing import Optional
from app.utils.logger import get_logger
from app.models.database import SessionLocal
from app.models.user import User
from app.integrations.messaging.base_channel import OutgoingMessage, MessageType

logger = get_logger(__name__)


class UserBindingHandler:
    """用户绑定验证处理器"""

    def __init__(self, channel_adapter):
        """
        初始化用户绑定处理器

        Args:
            channel_adapter: 渠道适配器（用于发送消息）
        """
        self.channel = channel_adapter

    async def verify_binding(
        self,
        sender_id: str,
        channel_type: str,
        chat_id: str
    ) -> Optional[any]:
        """
        验证用户是否已绑定

        Args:
            sender_id: 渠道用户ID
            channel_type: 渠道类型
            chat_id: 会话ID

        Returns:
            User 对象或 None
        """
        try:
            db = SessionLocal()
            try:
                # 根据渠道类型查询对应的字段
                if channel_type == "feishu":
                    user = db.query(User).filter(
                        User.feishu_user_id == sender_id
                    ).first()
                elif channel_type == "slack":
                    user = db.query(User).filter(
                        User.slack_user_id == sender_id
                    ).first()
                else:
                    # 通用查询（使用 email 或其他字段）
                    user = db.query(User).filter(
                        User.email == sender_id
                    ).first()

                if not user:
                    logger.warning(f"⚠️ 用户 {sender_id} ({channel_type}) 未绑定系统账号")
                    await self._send_unbind_warning(chat_id, channel_type)
                    return None

                if not user.is_active:
                    logger.warning(f"⚠️ 用户 {user.username} ({channel_type}: {sender_id}) 账号已被禁用")
                    await self._send_disabled_warning(chat_id)
                    return None

                logger.info(f"✅ 用户 {sender_id} ({channel_type}) 已绑定到系统用户 {user.username}")
                return user

            finally:
                db.close()

        except Exception as exc:
            logger.exception(f"❌ 验证用户绑定失败: {exc}")
            await self._send_error_message(chat_id)
            return None

    async def _send_unbind_warning(
        self,
        chat_id: str,
        channel_type: str
    ) -> None:
        """发送未绑定警告"""
        # 根据渠道类型发送不同语言的提示
        messages = {
            "feishu": (
                "❌ 您还未绑定系统账号\n\n"
                "请先在 Web 管理后台绑定您的飞书账号，才能使用飞书聊天功能。\n\n"
                "绑定步骤：\n"
                "1. 登录 Web 管理后台\n"
                "2. 进入「个人设置」\n"
                "3. 点击「绑定飞书账号」\n"
                "4. 完成绑定后即可使用\n\n"
                "如有疑问，请联系管理员。"
            ),
            "slack": (
                "❌ You haven't linked your account\n\n"
                "Please link your account in the web portal to use the chat feature.\n\n"
                "Steps:\n"
                "1. Log in to the web portal\n"
                "2. Go to 'Profile Settings'\n"
                "3. Click 'Link Slack Account'\n"
                "4. Complete the linking process\n\n"
                "Contact admin if you have questions."
            ),
            "wechat": (
                "❌ 您还未绑定系统账号\n\n"
                "请先在 Web 管理后台绑定您的微信账号。"
            ),
            "dingtalk": (
                "❌ 您还未绑定系统账号\n\n"
                "请先在 Web 管理后台绑定您的钉钉账号。"
            ),
        }

        message = messages.get(
            channel_type,
            "❌ 您还未绑定系统账号\n\n请先在 Web 管理后台绑定您的账号。"
        )

        await self._send_message(chat_id, message)

    async def _send_disabled_warning(self, chat_id: str) -> None:
        """发送账号禁用警告"""
        message = "❌ 您的账号已被禁用\n\n如有疑问，请联系管理员。"
        await self._send_message(chat_id, message)

    async def _send_error_message(self, chat_id: str) -> None:
        """发送错误消息"""
        message = "❌ 系统错误\n\n验证用户绑定时出现错误，请稍后重试或联系管理员。"
        await self._send_message(chat_id, message)

    async def _send_message(self, chat_id: str, text: str) -> None:
        """发送消息（通过渠道适配器）"""
        outgoing = OutgoingMessage(
            chat_id=chat_id,
            message_type=MessageType.TEXT,
            content={"text": text}
        )

        try:
            await self.channel.send_message(outgoing)
        except Exception as e:
            logger.error(f"发送用户绑定警告失败: {e}")
