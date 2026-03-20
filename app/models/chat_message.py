# app/models/chat_message.py
"""聊天消息模型"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from datetime import datetime
import enum
from app.models.database import Base


class MessageRole(str, enum.Enum):
    """消息角色枚举"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(Base):
    """聊天消息模型"""

    __tablename__ = "chat_messages"

    # 主键
    id = Column(Integer, primary_key=True, index=True)

    # 会话关联
    session_id = Column(
        String(100),
        ForeignKey("chat_sessions.session_id"),
        nullable=False,
        index=True,
        comment="会话ID",
    )

    # 消息内容
    role = Column(Enum(MessageRole), nullable=False, comment="消息角色")
    content = Column(Text, nullable=False, comment="消息内容")

    # 元数据（JSON 格式存储工具调用、错误信息等）
    meta_data = Column(Text, nullable=True, comment="元数据（JSON格式）")

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, index=True, comment="创建时间")

    def __repr__(self):
        return f"<ChatMessage(id={self.id}, session_id='{self.session_id}', role='{self.role}')>"
