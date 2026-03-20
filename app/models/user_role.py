# app/models/user_role.py
"""用户-角色关联模型"""

from sqlalchemy import Column, Integer, ForeignKey, DateTime, UniqueConstraint
from datetime import datetime
from app.models.database import Base


class UserRole(Base):
    """用户-角色关联模型"""

    __tablename__ = "user_roles"

    # 主键
    id = Column(Integer, primary_key=True, index=True)

    # 外键
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="用户ID")
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, comment="角色ID")

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    # 唯一约束
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    def __repr__(self):
        return f"<UserRole(user_id={self.user_id}, role_id={self.role_id})>"
