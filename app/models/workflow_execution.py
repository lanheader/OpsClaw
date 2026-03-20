# app/models/workflow_execution.py
"""工作流执行追踪模型"""

from sqlalchemy import Column, Integer, String, DateTime, JSON, Text
from sqlalchemy.sql import func
from datetime import datetime
from app.models.database import Base


class WorkflowExecution(Base):
    """
    追踪 LangGraph 工作流执行。

    存储工作流状态快照和执行元数据以支持：
    - 工作流历史查询
    - 执行分析
    - 调试和重放
    - 崩溃恢复协调
    """

    __tablename__ = "workflow_executions"

    # 主键
    id = Column(Integer, primary_key=True, index=True)

    # 任务标识符
    task_id = Column(
        String(100), unique=True, nullable=False, index=True, comment="唯一工作流任务 ID"
    )

    # 工作流元数据
    workflow_type = Column(
        String(50), nullable=False, comment="工作流类型：main、inspection、emergency 等"
    )
    workflow_version = Column(String(20), nullable=False, default="1.0", comment="工作流版本")

    # 当前状态（JSON 快照）
    state = Column(JSON, nullable=True, comment="当前工作流状态（OpsState）")

    # LangGraph checkpoint
    checkpoint_id = Column(
        String(100), nullable=True, index=True, comment="用于恢复的 LangGraph checkpoint ID"
    )

    # 执行状态
    status = Column(
        String(20),
        nullable=False,
        default="running",
        comment="状态：running、paused、completed、failed、cancelled",
    )

    # 错误信息
    error_message = Column(Text, nullable=True, comment="如果失败则为错误消息")

    # 时间戳
    created_at = Column(DateTime, nullable=False, default=func.now(), comment="工作流开始时间")
    updated_at = Column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="最后更新时间"
    )
    completed_at = Column(DateTime, nullable=True, comment="工作流完成时间")

    # 执行指标
    duration_seconds = Column(Integer, nullable=True, comment="总执行时长（秒）")

    def __repr__(self):
        return f"<WorkflowExecution(id={self.id}, task={self.task_id}, type={self.workflow_type}, status={self.status})>"

    def to_dict(self):
        """转换为字典用于 API 响应"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "workflow_type": self.workflow_type,
            "workflow_version": self.workflow_version,
            "status": self.status,
            "checkpoint_id": self.checkpoint_id,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "state": self.state,  # 可选包含完整状态
        }

    def calculate_duration(self):
        """如果已完成则计算并更新时长"""
        if self.completed_at and self.created_at:
            delta = self.completed_at - self.created_at
            self.duration_seconds = int(delta.total_seconds())
