"""提示词管理模型

支持将提示词存储到数据库，实现：
- 动态修改提示词（无需重启服务）
- 版本管理和回滚
- 审计日志
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.models.database import Base


class AgentPrompt(Base):
    """提示词主表"""

    __tablename__ = "agent_prompts"

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 基本信息
    agent_name = Column(String(50), unique=True, nullable=False, index=True, comment="Agent 标识符")
    name = Column(String(100), nullable=False, comment="显示名称")
    description = Column(Text, nullable=True, comment="描述")

    # 提示词内容
    content = Column(Text, nullable=False, comment="提示词内容")

    # 版本管理
    version = Column(Integer, nullable=False, default=1, comment="当前版本号")
    is_active = Column(Boolean, nullable=False, default=True, comment="是否激活")

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间"
    )

    # 关联版本历史
    versions = relationship(
        "PromptVersion",
        back_populates="agent_prompt",
        cascade="all, delete-orphan",
        order_by="desc(PromptVersion.version)"
    )

    __table_args__ = (
        Index("idx_agent_prompts_name", "agent_name"),
        Index("idx_agent_prompts_version", "agent_name", "version"),
    )

    def __repr__(self):  # type: ignore[no-untyped-def]
        return f"<AgentPrompt(agent_name='{self.agent_name}', version={self.version})>"

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "agent_name": self.agent_name,
            "name": self.name,
            "description": self.description,
            "content": self.content,
            "version": self.version,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PromptVersion(Base):
    """提示词版本历史表"""

    __tablename__ = "prompt_versions"

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 关联
    prompt_id = Column(Integer, ForeignKey("agent_prompts.id"), nullable=False, index=True)
    agent_name = Column(String(50), nullable=False, index=True)

    # 版本信息
    version = Column(Integer, nullable=False, comment="版本号")
    content = Column(Text, nullable=False, comment="提示词快照")

    # 变更信息
    change_summary = Column(String(500), nullable=True, comment="变更摘要")
    changed_by = Column(String(100), nullable=True, comment="修改人")

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    # 反向关联
    agent_prompt = relationship("AgentPrompt", back_populates="versions")

    __table_args__ = (
        Index("idx_prompt_versions_prompt", "prompt_id"),
        Index("idx_prompt_versions_version", "agent_name", "version"),
    )

    def __repr__(self):  # type: ignore[no-untyped-def]
        return f"<PromptVersion(agent_name='{self.agent_name}', version={self.version})>"

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "prompt_id": self.prompt_id,
            "agent_name": self.agent_name,
            "version": self.version,
            "content": self.content,
            "change_summary": self.change_summary,
            "changed_by": self.changed_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
