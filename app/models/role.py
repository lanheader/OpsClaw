# app/models/role.py
"""角色模型"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.models.database import Base


class Role(Base):
    """角色模型"""

    __tablename__ = "roles"

    # 主键
    id = Column(Integer, primary_key=True, index=True)

    # 基本信息
    name = Column(String(50), unique=True, nullable=False, comment="角色名称")
    code = Column(String(50), unique=True, nullable=False, comment="角色代码")
    description = Column(String(200), nullable=True, comment="角色描述")
    is_system = Column(Boolean, default=False, comment="是否系统预定义角色")

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间"
    )

    def __repr__(self):
        return f"<Role(id={self.id}, code='{self.code}', name='{self.name}')>"
