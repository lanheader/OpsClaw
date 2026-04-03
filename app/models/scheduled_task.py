# app/models/scheduled_task.py
"""
定时任务数据库模型

支持：
1. Cron 表达式（如：0 8 * * 1-5 表示工作日早上8点）
2. 任务执行记录
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.models.database import Base


class TaskType(str, enum.Enum):
    """任务类型 - 按需求文档定义"""
    K8S_INSPECT = "k8s_inspect"           # K8s 集群巡检
    RESOURCE_REPORT = "resource_report"   # 资源使用报告
    POD_RESTART = "pod_restart"           # Pod 重启检测
    CUSTOM_COMMAND = "custom_command"     # 自定义命令
    WEBHOOK = "webhook"                   # Webhook 推送


class ExecutionStatus(str, enum.Enum):
    """执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class ScheduledTask(Base):
    """定时任务表 - 按需求文档定义"""
    __tablename__ = "scheduled_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 基本信息
    name = Column(String(100), nullable=False, comment="任务名称")
    description = Column(Text, nullable=True, comment="任务描述")

    # 任务配置
    task_type = Column(
        String(50),
        nullable=False,
        comment="任务类型: k8s_inspect/resource_report/pod_restart/custom_command/webhook"
    )
    cron_expr = Column(String(100), nullable=False, comment="Cron 表达式，如 0 8 * * 1-5")
    timezone = Column(String(50), default="Asia/Shanghai", comment="时区")

    # 任务参数
    task_params = Column(Text, nullable=True, comment="JSON 格式，任务参数")

    # 执行控制
    enabled = Column(Boolean, default=True, comment="是否启用")
    timeout = Column(Integer, default=600, comment="超时时间(秒)")

    # 通知配置
    notify_on_fail = Column(Boolean, default=False, comment="失败是否飞书通知")
    notify_target = Column(String(200), nullable=True, comment="通知目标（飞书 user_id 或 chat_id）")

    # 执行统计
    last_run_time = Column(DateTime, nullable=True, comment="上次执行时间")
    last_run_status = Column(String(20), nullable=True, comment="上次执行状态")
    next_run_time = Column(DateTime, nullable=True, comment="下次执行时间")
    run_count = Column(Integer, default=0, comment="执行次数")
    success_count = Column(Integer, default=0, comment="成功次数")
    failure_count = Column(Integer, default=0, comment="失败次数")

    # 审计
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    # 关联执行记录
    executions = relationship("TaskExecution", back_populates="task", cascade="all, delete-orphan")

    def __repr__(self):  # type: ignore[no-untyped-def]
        return f"<ScheduledTask(id={self.id}, name={self.name}, type={self.task_type})>"


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
