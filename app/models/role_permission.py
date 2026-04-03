# app/models/role_permission.py
"""角色-权限关联模型"""

from sqlalchemy import Column, Integer, ForeignKey, DateTime, UniqueConstraint
from datetime import datetime
from app.models.database import Base


class RolePermission(Base):
    """角色-权限关联模型"""

    __tablename__ = "role_permissions"

    # 主键
    id = Column(Integer, primary_key=True, index=True)

    # 外键
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, comment="角色ID")
    permission_id = Column(Integer, ForeignKey("permissions.id"), nullable=False, comment="权限ID")

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    # 唯一约束
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    def __repr__(self):  # type: ignore[no-untyped-def]
        return f"<RolePermission(role_id={self.role_id}, permission_id={self.permission_id})>"
