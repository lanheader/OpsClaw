# app/schemas/scheduled_task.py
"""
定时任务的 Pydantic Schema
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from enum import Enum

from app.models.scheduled_task import TaskStatus, TaskType


class TaskStatusEnum(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DISABLED = "disabled"


class TaskTypeEnum(str, Enum):
    CRON = "cron"
    ONCE = "once"


# ========== 创建任务 ==========

class ScheduledTaskCreate(BaseModel):
    """创建定时任务请求"""
    name: str = Field(..., min_length=1, max_length=200, description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")

    # 调度配置（二选一）
    task_type: TaskTypeEnum = Field(..., description="任务类型: cron/once")
    cron_expression: Optional[str] = Field(None, description="Cron 表达式（cron 类型必填）")
    scheduled_time: Optional[datetime] = Field(None, description="指定执行时间（once 类型必填）")

    # 执行配置
    agent_task: str = Field(..., min_length=1, description="要执行的 Agent 任务描述")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict, description="任务参数")

    @field_validator('cron_expression')
    @classmethod
    def validate_cron(cls, v, info):
        if info.data.get('task_type') == TaskTypeEnum.CRON and not v:
            raise ValueError('cron_expression is required for cron task type')
        return v

    @field_validator('scheduled_time')
    @classmethod
    def validate_scheduled_time(cls, v, info):
        if info.data.get('task_type') == TaskTypeEnum.ONCE and not v:
            raise ValueError('scheduled_time is required for once task type')
        return v


# ========== 更新任务 ==========

class ScheduledTaskUpdate(BaseModel):
    """更新定时任务请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    cron_expression: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    agent_task: Optional[str] = Field(None, min_length=1)
    parameters: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None


# ========== 响应模型 ==========

class ScheduledTaskResponse(BaseModel):
    """定时任务响应"""
    id: int
    name: str
    description: Optional[str] = None
    task_type: str
    cron_expression: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    agent_task: str
    parameters: Dict[str, Any] = {}
    status: str
    enabled: bool
    last_run_time: Optional[datetime] = None
    last_run_status: Optional[str] = None
    last_run_result: Optional[str] = None
    next_run_time: Optional[datetime] = None
    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    created_by: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScheduledTaskListResponse(BaseModel):
    """定时任务列表响应"""
    tasks: List[ScheduledTaskResponse]
    total: int


# ========== 执行日志 ==========

class TaskExecutionLogResponse(BaseModel):
    """任务执行日志响应"""
    id: int
    task_id: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    status: str
    result: Optional[str] = None
    error_message: Optional[str] = None
    session_id: Optional[str] = None

    class Config:
        from_attributes = True


class TaskExecutionLogListResponse(BaseModel):
    """执行日志列表响应"""
    logs: List[TaskExecutionLogResponse]
    total: int


# ========== Agent 工具调用 ==========

class CreateTaskFromChat(BaseModel):
    """从对话中创建定时任务"""
    name: str = Field(..., description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")
    schedule: str = Field(..., description="调度时间，如 '每天9点'、'2024-01-01 10:00'、'0 9 * * *'")
    task: str = Field(..., description="要执行的任务描述")


class TaskOperationResult(BaseModel):
    """任务操作结果"""
    success: bool
    message: str
    task_id: Optional[int] = None
    next_run_time: Optional[datetime] = None
