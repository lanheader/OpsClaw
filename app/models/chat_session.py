# app/models/chat_session.py
"""聊天会话模型"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Enum
from datetime import datetime
from app.models.database import Base
import enum


class SessionState(str, enum.Enum):
    """会话状态枚举"""

    NORMAL = "normal"  # 正常对话
    AWAITING_APPROVAL = "awaiting_approval"  # 等待批准
    PROCESSING = "processing"  # 处理中


class ChatSession(Base):
    """聊天会话模型"""

    __tablename__ = "chat_sessions"

    # 主键
    id = Column(Integer, primary_key=True, index=True)

    # 会话标识
    session_id = Column(
        String(100), unique=True, index=True, nullable=False, comment="会话唯一标识"
    )

    # 用户关联
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="用户ID")

    # 会话信息
    title = Column(String(200), nullable=True, comment="会话标题（从首条消息生成）")

    # 会话来源
    source = Column(String(20), default="web", nullable=False, comment="会话来源：web, feishu")
    external_chat_id = Column(
        String(100), nullable=True, index=True, comment="外部聊天ID（飞书chat_id）"
    )
    external_user_id = Column(String(100), nullable=True, comment="外部用户ID（飞书sender_id）")
    external_user_name = Column(String(100), nullable=True, comment="外部用户名称（飞书用户名）")

    # 状态字段
    is_active = Column(Boolean, default=True, comment="是否活跃")

    # 会话状态（用于批准流程）
    state = Column(
        String(20),
        default=SessionState.NORMAL.value,
        nullable=False,
        comment="会话状态：normal, awaiting_approval, processing",
    )
    pending_approval_data = Column(JSON, nullable=True, comment="待批准数据（命令、风险等级等）")
    approval_expires_at = Column(DateTime, nullable=True, comment="批准请求过期时间")

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间"
    )

    def __repr__(self):
        return f"<ChatSession(id={self.id}, session_id='{self.session_id}', source='{self.source}', user_id={self.user_id})>"
