"""飞书回调扩展功能 - 会话管理"""

import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy import func

from app.utils.logger import get_logger
from app.models.database import SessionLocal
from app.models.chat_session import ChatSession, SessionState
from app.models.chat_message import ChatMessage, MessageRole
from app.models.user import User

logger = get_logger(__name__)


async def handle_new_session_command(  # type: ignore[no-untyped-def]
    chat_id: str, sender_id: str, sender_name: Optional[str], send_reply_func
):
    """
    处理 /new 命令 - 创建新会话

    Args:
        chat_id: 飞书 chat_id
        sender_id: 发送者 ID
        sender_name: 发送者名称
        send_reply_func: 发送回复的函数
    """
    logger.info(f"🆕 处理 /new 命令: chat_id={chat_id}")

    db = SessionLocal()
    try:
        # 结束当前会话（软删除）
        current_session = (
            db.query(ChatSession)
            .filter(
                ChatSession.external_chat_id == chat_id,
                ChatSession.source == "feishu",
                ChatSession.is_active == True,
            )
            .first()
        )

        if current_session:
            current_session.is_active = False  # type: ignore[assignment]
            current_session.state = SessionState.NORMAL.value  # type: ignore[assignment]
            current_session.pending_approval_data = None  # type: ignore[assignment]
            db.commit()
            logger.info(f"✅ 已结束旧会话: {current_session.session_id}")

        # 创建新会话
        new_session_id = f"feishu_{uuid.uuid4().hex[:16]}"

        # 获取默认用户
        default_user = db.query(User).filter(User.username == "admin").first()
        if not default_user:
            default_user = db.query(User).first()

        if not default_user:
            await send_reply_func(chat_id, "❌ 系统错误：无法创建会话")
            return

        # 生成会话标题
        title = f"飞书对话 - {sender_name}" if sender_name else f"飞书对话 {chat_id[:8]}"

        new_session = ChatSession(
            session_id=new_session_id,
            user_id=default_user.id,
            title=title,
            source="feishu",
            external_chat_id=chat_id,
            external_user_id=sender_id,
            external_user_name=sender_name,
            is_active=True,
            state=SessionState.NORMAL.value,
        )

        db.add(new_session)
        db.commit()
        db.refresh(new_session)

        logger.info(f"✅ 已创建新会话: {new_session_id}")

        # 发送确认消息
        message = f"""✅ **新会话已创建**

会话ID: {new_session_id}
创建时间: {new_session.created_at.strftime('%Y-%m-%d %H:%M:%S')}

现在可以开始新的对话了！之前的对话历史已保存。

💡 提示：
- 使用 /help 查看帮助
- 使用 /end 结束当前会话
"""
        await send_reply_func(chat_id, message)

    except Exception as e:
        logger.error(f"❌ 创建新会话失败: {e}", exc_info=True)
        await send_reply_func(chat_id, f"❌ 创建新会话失败: {str(e)}")
    finally:
        db.close()


async def handle_end_session_command(chat_id: str, session_id: str, send_reply_func):  # type: ignore[no-untyped-def]
    """
    处理 /end 命令 - 结束当前会话

    Args:
        chat_id: 飞书 chat_id
        session_id: 会话 ID
        send_reply_func: 发送回复的函数
    """
    logger.info(f"🔚 处理 /end 命令: session_id={session_id}")

    db = SessionLocal()
    try:
        # 查找当前会话
        session = (
            db.query(ChatSession)
            .filter(ChatSession.session_id == session_id, ChatSession.is_active == True)
            .first()
        )

        if not session:
            await send_reply_func(chat_id, "❌ 当前没有活跃的会话")
            return

        # 获取会话统计信息
        message_count = (
            db.query(func.count(ChatMessage.id))
            .filter(ChatMessage.session_id == session_id)
            .scalar()
        )

        created_at = session.created_at
        duration = datetime.utcnow() - created_at
        duration_str = (
            f"{duration.days}天"
            if duration.days > 0
            else f"{duration.seconds // 3600}小时{(duration.seconds % 3600) // 60}分钟"
        )

        # 结束会话（软删除）
        session.is_active = False  # type: ignore[assignment]
        session.state = SessionState.NORMAL.value  # type: ignore[assignment]
        session.pending_approval_data = None  # type: ignore[assignment]
        db.commit()

        logger.info(f"✅ 已结束会话: {session_id}")

        # 发送确认消息
        message = f"""✅ **会话已结束**

会话ID: {session_id}
消息数量: {message_count}
持续时间: {duration_str}
创建时间: {created_at.strftime('%Y-%m-%d %H:%M:%S')}

会话历史已保存，您可以：
- 使用 /new 创建新会话
- 继续发送消息（将自动创建新会话）
"""
        await send_reply_func(chat_id, message)

    except Exception as e:
        logger.error(f"❌ 结束会话失败: {e}", exc_info=True)
        await send_reply_func(chat_id, f"❌ 结束会话失败: {str(e)}")
    finally:
        db.close()
