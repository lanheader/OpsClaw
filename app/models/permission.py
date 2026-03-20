# app/models/permission.py
"""权限模型"""

from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from app.models.database import Base


class Permission(Base):
    """权限模型"""

    __tablename__ = "permissions"

    # 主键
    id = Column(Integer, primary_key=True, index=True)

    # 基本信息
    name = Column(String(100), nullable=False, comment="权限名称")
    code = Column(String(100), unique=True, nullable=False, comment="权限代码")
    category = Column(String(50), nullable=False, comment="权限分类: menu/tool/api")
    resource = Column(String(100), nullable=False, comment="资源标识")
    description = Column(String(200), nullable=True, comment="权限描述")

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    def __repr__(self):
        return f"<Permission(id={self.id}, code='{self.code}', category='{self.category}')>"
