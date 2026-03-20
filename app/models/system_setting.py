"""系统设置模型"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from datetime import datetime
from app.models.database import Base


class SystemSetting(Base):
    """系统设置模型"""

    __tablename__ = "system_settings"

    # 主键
    id = Column(Integer, primary_key=True, index=True)

    # 设置信息
    key = Column(String(100), unique=True, index=True, nullable=False, comment="设置键")
    value = Column(Text, nullable=True, comment="设置值")
    category = Column(String(50), nullable=False, comment="设置分类")
    name = Column(String(100), nullable=False, comment="设置名称")
    description = Column(Text, nullable=True, comment="设置描述")
    value_type = Column(
        String(20),
        nullable=False,
        default="string",
        comment="值类型: string, number, boolean, json",
    )
    is_sensitive = Column(Boolean, default=False, comment="是否敏感信息（如密码、密钥）")
    is_readonly = Column(Boolean, default=False, comment="是否只读")

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间"
    )

    def __repr__(self):
        return f"<SystemSetting(key='{self.key}', category='{self.category}')>"
