"""聊天会话域模型"""

from app.models.database import get_chat_db, session_makers, engines, bases
from app.models.chat.session import ChatSession, SessionState
from app.models.chat.message import ChatMessage, MessageRole

# 域级数据库访问
get_db = get_chat_db
engine = engines["chat"]
SessionLocal = session_makers["chat"]
Base = bases["chat"]

__all__ = [
    "ChatSession",
    "SessionState",
    "ChatMessage",
    "MessageRole",
    "get_db",
    "engine",
    "SessionLocal",
    "Base",
]
