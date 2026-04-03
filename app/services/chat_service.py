# app/services/chat_service.py
"""聊天服务 - 用于保存和管理聊天会话"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import desc
from sqlalchemy.orm import Session
from app.models.chat_session import ChatSession
from app.models.chat_message import ChatMessage, MessageRole
from app.models.user import User
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def get_or_create_feishu_session(
    db: Session,
    chat_id: str,
    sender_id: str,
    sender_name: Optional[str] = None,
    title: Optional[str] = None,
) -> ChatSession:
    """
    获取或创建飞书会话

    Args:
        db: 数据库会话
        chat_id: 飞书 chat_id
        sender_id: 飞书 sender_id
        sender_name: 飞书用户名（可选）
        title: 会话标题

    Returns:
        ChatSession 对象
    """
    # 优先查找活跃会话
    session = (
        db.query(ChatSession)
        .filter(
            ChatSession.external_chat_id == chat_id,
            ChatSession.source == "feishu",
            ChatSession.is_active == True,
        )
        .first()
    )

    if session:
        logger.info(f"Found active Feishu session: {session.session_id}")
        # 如果会话存在但没有用户名，更新用户名
        if sender_name and not session.external_user_name:
            session.external_user_name = sender_name  # type: ignore[assignment]
            db.commit()
            logger.info(f"Updated Feishu session user name: {sender_name}")
        return session

    # 没有活跃会话，检查是否有非活跃会话
    inactive_session = (
        db.query(ChatSession)
        .filter(
            ChatSession.external_chat_id == chat_id,
            ChatSession.source == "feishu",
        )
        .order_by(desc(ChatSession.created_at))
        .first()
    )

    if inactive_session:
        # 重新激活最近的非活跃会话
        inactive_session.is_active = True  # type: ignore[assignment]
        inactive_session.state = "normal"  # type: ignore[assignment]
        inactive_session.pending_approval_data = None  # type: ignore[assignment]
        if sender_name:
            inactive_session.external_user_name = sender_name  # type: ignore[assignment]
        db.commit()
        db.refresh(inactive_session)
        logger.info(f"Reactivated inactive Feishu session: {inactive_session.session_id}")
        return inactive_session

    # 创建新会话
    # 使用默认用户（admin）或创建一个飞书专用用户
    default_user = db.query(User).filter(User.username == "admin").first()
    if not default_user:
        # 如果没有 admin 用户，使用第一个用户
        default_user = db.query(User).first()

    if not default_user:
        raise ValueError("No user found in database. Please create a user first.")

    session_id = f"feishu_{uuid.uuid4().hex[:16]}"

    # 生成会话标题
    if not title:
        if sender_name:
            title = f"飞书对话 - {sender_name}"
        else:
            title = f"飞书对话 {chat_id[:8]}"

    new_session = ChatSession(
        session_id=session_id,
        user_id=default_user.id,
        title=title,
        source="feishu",
        external_chat_id=chat_id,
        external_user_id=sender_id,
        external_user_name=sender_name,
        is_active=True,
    )

    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    logger.info(f"Created new Feishu session: {session_id} for user {sender_name or sender_id}")
    return new_session


def save_feishu_message(
    db: Session, session_id: str, role: MessageRole, content: str, meta_data: Optional[str] = None
) -> ChatMessage:
    """
    保存飞书消息

    Args:
        db: 数据库会话
        session_id: 会话ID
        role: 消息角色
        content: 消息内容
        meta_data: 元数据（可选，如飞书消息ID）

    Returns:
        ChatMessage 对象
    """
    message = ChatMessage(session_id=session_id, role=role, content=content, meta_data=meta_data)

    db.add(message)
    db.commit()
    db.refresh(message)

    # 更新会话的 updated_at 时间
    session = (
        db.query(ChatSession)
        .filter(ChatSession.session_id == session_id)
        .first()
    )

    if session:
        session.updated_at = datetime.now(timezone.utc)  # type: ignore[assignment]

        # 如果会话没有标题，使用第一条消息作为标题
        if not session.title and role == MessageRole.USER:
            session.title = content[:30] + ("..." if len(content) > 30 else "")  # type: ignore[assignment]

        db.commit()

    logger.info(f"Saved Feishu message: session={session_id}, role={role.value}")
    return message
