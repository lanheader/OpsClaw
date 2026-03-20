# app/models/audit_log.py
"""用于追踪所有操作的安全审计日志模型"""

from sqlalchemy import Column, Integer, String, DateTime, JSON, Text
from sqlalchemy.sql import func
from datetime import datetime
from app.models.database import Base


class AuditLog(Base):
    """
    所有操作的安全审计日志。

    记录由 Security Agent 审核的每个动作，包括：
    - 命令审核结果
    - 风险评估
    - 审批决策
    - 用户上下文

    这为合规性和调试提供了完整的审计追踪。
    """

    __tablename__ = "audit_logs"

    # 主键
    id = Column(Integer, primary_key=True, index=True)

    # 任务上下文
    task_id = Column(String(100), nullable=False, index=True, comment="工作流任务 ID")
    agent_name = Column(String(50), nullable=False, comment="执行动作的智能体")

    # 操作详情
    operation = Column(
        String(100), nullable=False, comment="操作类型（例如 'restart'、'scale'、'delete'）"
    )
    resource = Column(
        String(200), nullable=False, comment="目标资源（例如 'redis-prod'、'mysql-db'）"
    )

    # 用户上下文
    user_id = Column(String(100), nullable=True, index=True, comment="触发操作的用户")

    # 安全评估
    risk_level = Column(Integer, nullable=False, comment="风险等级（0-10）")
    approved = Column(Integer, nullable=False, comment="如果批准则为 1，拒绝则为 0")
    reason = Column(Text, nullable=True, comment="批准/拒绝的原因")

    # 动作详情（JSON）
    action_detail = Column(JSON, nullable=True, comment="包括命令的完整动作详情")

    # 时间戳
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Audit log creation time"
    )

    def __repr__(self):
        return f"<AuditLog(id={self.id}, task={self.task_id}, operation={self.operation}, risk={self.risk_level}, approved={self.approved})>"

    def to_dict(self):
        """转换为字典用于 API 响应"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "operation": self.operation,
            "resource": self.resource,
            "user_id": self.user_id,
            "risk_level": self.risk_level,
            "approved": bool(self.approved),
            "reason": self.reason,
            "action_detail": self.action_detail,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
