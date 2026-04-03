"""
会话管理处理器

职责：
- 获取或创建会话
- 构建渠道上下文
"""

import uuid
from typing import Optional
from app.utils.logger import get_logger
from app.services.chat_service import get_or_create_feishu_session
from app.core.permission_checker import get_user_permission_codes

from app.integrations.messaging.base_channel import ChannelContext
from app.models.database import SessionLocal
from app.models.chat_session import ChatSession

logger = get_logger(__name__)


class SessionHandler:
    """会话管理处理器"""

    async def get_or_create_context(
        self,
        chat_id: str,
        sender_id: str,
        sender_name: Optional[str],
        channel_type: str,
        user_id: int,
        db: Optional[SessionLocal] = None  # type: ignore[valid-type]
    ) -> ChannelContext:
        """
        获取或创建会话上下文

        Args:
            chat_id: 渠道会话ID
            sender_id: 渠道用户ID
            sender_name: 发送者名称
            channel_type: 渠道类型
            user_id: 系统用户ID
            db: 数据库会话（可选，如果不提供则内部创建）

        Returns:
            ChannelContext 对象
        """
        should_close_db = False
        if db is None:
            db = SessionLocal()
            should_close_db = True

        try:
            # 查找活跃会话
            session = db.query(ChatSession).filter(
                ChatSession.external_chat_id == chat_id,
                ChatSession.source == channel_type,
                ChatSession.is_active == True
            ).first()

            if session:
                logger.info(f"✅ 找到现有会话: {session.session_id}")
                return self._build_context(session, db)

            # 创建新会话
            session_id = f"{channel_type}_{uuid.uuid4().hex[:16]}"
            session_title = f"{channel_type.upper()} 对话 - {sender_name or chat_id[:8]}"

            logger.info(f"📝 创建新会话: {session_id}")

            session = ChatSession(
                session_id=session_id,
                user_id=user_id,
                title=session_title,
                source=channel_type,
                external_chat_id=chat_id,
                external_user_id=sender_id,
                external_user_name=sender_name,
                is_active=True
            )

            db.add(session)
            db.commit()
            db.refresh(session)

            return self._build_context(session, db)

        finally:
            if should_close_db:
                db.close()

    def _build_context(
        self,
        session: ChatSession,
        db: SessionLocal  # type: ignore[valid-type]
    ) -> ChannelContext:
        """
        构建渠道上下文

        Args:
            session: 会话对象
            db: 数据库会话

        Returns:
            ChannelContext 对象
        """
        # 获取用户权限
        try:
            permission_codes = get_user_permission_codes(db, session.user_id)  # type: ignore[arg-type]
        except Exception as e:
            logger.warning(f"获取用户权限失败: {e}，使用空权限")
            permission_codes = []

        context = ChannelContext(
            channel_type=session.source,  # type: ignore[arg-type]
            chat_id=session.external_chat_id,  # type: ignore[arg-type]
            sender_id=session.external_user_id,  # type: ignore[arg-type]
            session_id=session.session_id,  # type: ignore[arg-type]
            user_id=session.user_id,  # type: ignore[arg-type]
            user_permissions=set(permission_codes)
        )

        # 添加会话元数据
        context.metadata.update({
            "session_title": session.title,
            "session_created": session.created_at.isoformat() if session.created_at else None,
        })

        return context

    async def end_session(self, context: ChannelContext) -> bool:
        """
        结束会话

        Args:
            context: 渠道上下文

        Returns:
            是否成功
        """
        db = SessionLocal()
        try:
            session = db.query(ChatSession).filter(
                ChatSession.session_id == context.session_id
            ).first()

            if session:
                session.is_active = False  # type: ignore[assignment]
                db.commit()
                logger.info(f"✅ 会话已结束: {context.session_id}")
                return True

            return False

        except Exception as e:
            logger.exception(f"❌ 结束会话失败: {e}")
            return False
        finally:
            db.close()

    async def create_new_session(
        self,
        chat_id: str,
        sender_id: str,
        sender_name: Optional[str],
        channel_type: str,
        user_id: int
    ) -> ChannelContext:
        """
        强制创建新会话

        Args:
            chat_id: 渠道会话ID
            sender_id: 渠道用户ID
            sender_name: 发送者名称
            channel_type: 渠道类型
            user_id: 系统用户ID

        Returns:
            新的 ChannelContext 对象
        """
        db = SessionLocal()
        try:
            # 先结束当前活跃会话
            db.query(ChatSession).filter(
                ChatSession.external_chat_id == chat_id,
                ChatSession.source == channel_type,
                ChatSession.is_active == True
            ).update({"is_active": False})

            # 创建新会话
            session_id = f"{channel_type}_{uuid.uuid4().hex[:16]}"
            session_title = f"{channel_type.upper()} 对话 - {sender_name or chat_id[:8]}"

            session = ChatSession(
                session_id=session_id,
                user_id=user_id,
                title=session_title,
                source=channel_type,
                external_chat_id=chat_id,
                external_user_id=sender_id,
                external_user_name=sender_name,
                is_active=True
            )

            db.add(session)
            db.commit()
            db.refresh(session)

            logger.info(f"✅ 创建新会话: {session_id}")

            # 获取用户权限
            permission_codes = get_user_permission_codes(db, user_id)

            return ChannelContext(
                channel_type=channel_type,
                chat_id=chat_id,
                sender_id=sender_id,
                session_id=session_id,
                user_id=user_id,
                user_permissions=set(permission_codes)
            )

        finally:
            db.close()
