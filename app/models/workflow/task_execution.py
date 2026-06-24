# app/models/workflow/task_execution.py
"""任务执行记录模型"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.models.database import bases
Base = bases["workflow"]


class ExecutionStatus(str, enum.Enum):
    """执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class TaskExecution(Base):
    """任务执行记录表 - 按需求文档定义"""
    __tablename__ = "task_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("scheduled_tasks.id", ondelete="CASCADE"), nullable=False, index=True, comment="关联任务 ID")

    # 执行信息
    status = Column(String(20), nullable=False, default="pending", comment="状态: pending/running/success/failed/timeout")
    trigger_type = Column(String(20), nullable=False, default="scheduled", comment="触发类型: scheduled/manual")
    started_at = Column(DateTime, server_default=func.now(), comment="开始时间")
    finished_at = Column(DateTime, nullable=True, comment="结束时间")
    duration_ms = Column(Integer, nullable=True, comment="执行耗时毫秒")

    # 执行结果
    result_summary = Column(Text, nullable=True, comment="执行结果摘要")
    error_message = Column(Text, nullable=True, comment="错误信息")

    # 审计
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")

    # 关联任务
    task = relationship("ScheduledTask", back_populates="executions")

    def __repr__(self):  # type: ignore[no-untyped-def]
        return f"<TaskExecution(id={self.id}, task_id={self.task_id}, status={self.status})>"
