# app/models/user.py
"""用户模型"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime
from app.models.database import Base


class User(Base):
    """用户模型"""

    __tablename__ = "users"

    # 主键
    id = Column(Integer, primary_key=True, index=True)

    # 基本信息
    username = Column(String(50), unique=True, index=True, nullable=False, comment="用户名")
    email = Column(String(100), unique=True, index=True, nullable=False, comment="邮箱")
    hashed_password = Column(String(255), nullable=False, comment="加密后的密码")
    full_name = Column(String(100), nullable=True, comment="全名")

    # 飞书集成
    feishu_user_id = Column(
        String(100), unique=True, index=True, nullable=True, comment="飞书用户ID"
    )

    # 状态字段
    is_active = Column(Boolean, default=True, comment="是否启用")
    is_superuser = Column(Boolean, default=False, comment="是否超级管理员")

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间"
    )
    last_login_at = Column(DateTime, nullable=True, comment="最后登录时间")

    def __repr__(self):  # type: ignore[no-untyped-def]
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"
