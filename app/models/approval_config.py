"""审批配置数据模型"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime, Index
from app.models.database import Base


class ApprovalConfig(Base):
    """工具审批配置表"""

    __tablename__ = "approval_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tool_name = Column(String(100), unique=True, nullable=False, index=True)
    tool_group = Column(String(50))
    risk_level = Column(String(20))
    requires_approval = Column(Boolean, default=True, nullable=False)
    approval_roles = Column(JSON, nullable=True)
    exempt_roles = Column(JSON, nullable=True)
    description = Column(String(200))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_approval_tools_group", "tool_group"),
        Index("idx_approval_tools_risk", "risk_level"),
    )

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "tool_group": self.tool_group,
            "risk_level": self.risk_level,
            "requires_approval": self.requires_approval,
            "approval_roles": self.approval_roles,
            "exempt_roles": self.exempt_roles,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
