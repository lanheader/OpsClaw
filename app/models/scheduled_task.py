# app/models/scheduled_task.py
"""
定时任务数据库模型

支持两种调度方式：
1. Cron 表达式（如：0 9 * * * 表示每天 9:00）
2. 指定时间（一次性任务）
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, Enum as SQLEnum
from sqlalchemy.sql import func
import enum

from app.models.database import Base


class TaskStatus(str, enum.Enum):
    """任务状态"""
    PENDING = "pending"       # 等待执行
    RUNNING = "running"       # 执行中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"         # 执行失败
    CANCELLED = "cancelled"   # 已取消
    DISABLED = "disabled"     # 已禁用


class TaskType(str, enum.Enum):
    """任务类型"""
    CRON = "cron"             # Cron 表达式
    ONCE = "once"             # 一次性任务


class ScheduledTask(Base):
    """定时任务表"""
    __tablename__ = "scheduled_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 基本信息
    name = Column(String(200), nullable=False, comment="任务名称")
    description = Column(Text, nullable=True, comment="任务描述")

    # 调度配置
    task_type = Column(
        SQLEnum(TaskType),
        nullable=False,
        default=TaskType.CRON,
        comment="任务类型: cron/once"
    )
    cron_expression = Column(String(100), nullable=True, comment="Cron 表达式")
    scheduled_time = Column(DateTime, nullable=True, comment="指定执行时间（一次性任务）")

    # 执行配置
    agent_task = Column(Text, nullable=False, comment="要执行的 Agent 任务描述")
    parameters = Column(JSON, nullable=True, default=dict, comment="任务参数")

    # 状态管理
    status = Column(
        SQLEnum(TaskStatus),
        nullable=False,
        default=TaskStatus.PENDING,
        comment="任务状态"
    )
    enabled = Column(Boolean, default=True, comment="是否启用")

    # 执行统计
    last_run_time = Column(DateTime, nullable=True, comment="上次执行时间")
    last_run_status = Column(String(50), nullable=True, comment="上次执行状态")
    last_run_result = Column(Text, nullable=True, comment="上次执行结果")
    next_run_time = Column(DateTime, nullable=True, comment="下次执行时间")
    run_count = Column(Integer, default=0, comment="执行次数")
    success_count = Column(Integer, default=0, comment="成功次数")
    failure_count = Column(Integer, default=0, comment="失败次数")

    # 权限和审计
    created_by = Column(Integer, nullable=False, comment="创建人 ID")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    def __repr__(self):
        return f"<ScheduledTask(id={self.id}, name={self.name}, status={self.status})>"

    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "task_type": self.task_type.value if self.task_type else None,
            "cron_expression": self.cron_expression,
            "scheduled_time": self.scheduled_time.isoformat() if self.scheduled_time else None,
            "agent_task": self.agent_task,
            "parameters": self.parameters or {},
            "status": self.status.value if self.status else None,
            "enabled": self.enabled,
            "last_run_time": self.last_run_time.isoformat() if self.last_run_time else None,
            "last_run_status": self.last_run_status,
            "last_run_result": self.last_run_result,
            "next_run_time": self.next_run_time.isoformat() if self.next_run_time else None,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TaskExecutionLog(Base):
    """任务执行日志表"""
    __tablename__ = "task_execution_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, index=True, comment="关联任务 ID")

    # 执行信息
    started_at = Column(DateTime, server_default=func.now(), comment="开始时间")
    finished_at = Column(DateTime, nullable=True, comment="结束时间")
    duration_seconds = Column(Integer, nullable=True, comment="执行耗时（秒）")

    # 执行结果
    status = Column(String(50), nullable=False, comment="执行状态")
    result = Column(Text, nullable=True, comment="执行结果")
    error_message = Column(Text, nullable=True, comment="错误信息")

    # 关联会话
    session_id = Column(String(100), nullable=True, comment="关联的会话 ID")

    def __repr__(self):
        return f"<TaskExecutionLog(id={self.id}, task_id={self.task_id}, status={self.status})>"

    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_seconds": self.duration_seconds,
            "status": self.status,
            "result": self.result,
            "error_message": self.error_message,
            "session_id": self.session_id,
        }
