"""
运维知识库数据模型

存储历史故障案例，用于 RAG 增强诊断
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean
from sqlalchemy.orm import relationship

from app.models.database import Base


class IncidentKnowledgeBase(Base):
    """
    事故知识库

    存储历史故障案例，包括：
    - 问题描述
    - 症状
    - 根因分析
    - 解决方案
    - 有效性评分
    """
    __tablename__ = "incident_knowledge_base"

    id = Column(Integer, primary_key=True, index=True)
    issue_title = Column(String(255), nullable=False, comment="问题标题")
    issue_description = Column(Text, nullable=False, comment="问题描述")
    symptoms = Column(Text, nullable=True, comment="症状描述")
    root_cause = Column(Text, nullable=True, comment="根本原因")
    solution = Column(Text, nullable=True, comment="解决方案")
    effectiveness_score = Column(Float, default=0.5, comment="有效性评分 (0-1)")

    # 元数据
    severity = Column(String(50), nullable=True, comment="严重程度: low/medium/high/critical")
    affected_system = Column(String(100), nullable=True, comment="受影响系统")
    category = Column(String(100), nullable=True, comment="分类: network/storage/application/database等")

    # 状态
    is_verified = Column(Boolean, default=False, comment="是否已验证")
    is_active = Column(Boolean, default=True, comment="是否有效")

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    resolved_at = Column(DateTime, nullable=True, comment="解决时间")

    # 关联
    tags = Column(String(500), nullable=True, comment="标签，逗号分隔")

    def __repr__(self):  # type: ignore[no-untyped-def]
        return f"<IncidentKnowledgeBase(id={self.id}, title='{self.issue_title}', score={self.effectiveness_score})>"
