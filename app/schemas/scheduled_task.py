# app/schemas/scheduled_task.py
"""
定时任务的 Pydantic Schema - 按需求文档规范
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from enum import Enum
import re


class TaskTypeEnum(str, Enum):
    """任务类型枚举"""
    K8S_INSPECT = "k8s_inspect"
    RESOURCE_REPORT = "resource_report"
    POD_RESTART = "pod_restart"
    CUSTOM_COMMAND = "custom_command"
    WEBHOOK = "webhook"


class ExecutionStatusEnum(str, Enum):
    """执行状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class TriggerTypeEnum(str, Enum):
    """触发类型枚举"""
    SCHEDULED = "scheduled"
    MANUAL = "manual"


# ========== Cron 验证工具 ==========

def validate_cron_expression(expr: str) -> bool:
    """验证 5 字段 cron 表达式"""
    if not expr:
        return False
    parts = expr.strip().split()
    if len(parts) != 5:
        return False
    # 基本验证：每个字段应该是数字、*、逗号分隔的数字、或范围
    pattern = r'^[\d\*,/-]+$'
    return all(re.match(pattern, p) for p in parts)


# ========== 创建任务 ==========

class ScheduledTaskCreate(BaseModel):
    """创建定时任务请求"""
    name: str = Field(..., min_length=1, max_length=100, description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")

    # 任务配置
    task_type: TaskTypeEnum = Field(..., description="任务类型")
    cron_expr: str = Field(..., description="Cron 表达式，如 0 8 * * 1-5")
    timezone: str = Field(default="Asia/Shanghai", description="时区")

    # 任务参数
    task_params: Optional[Dict[str, Any]] = Field(default_factory=dict, description="JSON 格式任务参数")

    # 执行控制
    enabled: bool = Field(default=True, description="是否启用")
    timeout: int = Field(default=600, ge=1, le=86400, description="超时时间(秒)")

    # 通知配置
    notify_on_fail: bool = Field(default=False, description="失败是否飞书通知")
    notify_target: Optional[str] = Field(None, max_length=200, description="通知目标")

    @field_validator('cron_expr')
    @classmethod
    def validate_cron(cls, v):  # type: ignore[no-untyped-def]
        if not validate_cron_expression(v):
            raise ValueError(f'无效的 Cron 表达式: {v}。请使用标准 5 字段格式，如 "0 8 * * 1-5"')
        return v


# ========== 更新任务 ==========

class ScheduledTaskUpdate(BaseModel):
    """更新定时任务请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    cron_expr: Optional[str] = None
    timezone: Optional[str] = None
    task_params: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    timeout: Optional[int] = Field(None, ge=1, le=86400)
    notify_on_fail: Optional[bool] = None
    notify_target: Optional[str] = Field(None, max_length=200)

    @field_validator('cron_expr')
    @classmethod
    def validate_cron(cls, v):  # type: ignore[no-untyped-def]
        if v is not None and not validate_cron_expression(v):
            raise ValueError(f'无效的 Cron 表达式: {v}')
        return v


# ========== 响应模型 ==========

class ScheduledTaskResponse(BaseModel):
    """定时任务响应"""
    id: int
    name: str
    description: Optional[str] = None
    task_type: str
    cron_expr: str
    timezone: str = "Asia/Shanghai"
    task_params: Dict[str, Any] = {}
    enabled: bool
    timeout: int = 600
    notify_on_fail: bool = False
    notify_target: Optional[str] = None
    last_run_time: Optional[datetime] = None
    last_run_status: Optional[str] = None
    next_run_time: Optional[datetime] = None
    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ScheduledTaskListResponse(BaseModel):
    """定时任务列表响应"""
    tasks: List[ScheduledTaskResponse]
    total: int


# ========== 执行记录 ==========

class TaskExecutionResponse(BaseModel):
    """任务执行记录响应"""
    id: int
    task_id: int
    status: str
    trigger_type: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    result_summary: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    # 关联任务信息
    task_name: Optional[str] = None

    class Config:
        from_attributes = True


class TaskExecutionListResponse(BaseModel):
    """执行记录列表响应"""
    executions: List[TaskExecutionResponse]
    total: int


# ========== 统计信息 ==========

class TodayStats(BaseModel):
    """今日统计"""
    total: int = 0
    running: int = 0
    success: int = 0
    failed: int = 0


class TaskStatsResponse(BaseModel):
    """任务统计响应"""
    total: int = 0
    enabled: int = 0
    today_stats: TodayStats = TodayStats()


# ========== 操作结果 ==========

class TaskOperationResult(BaseModel):
    """任务操作结果"""
    success: bool
    message: str
    task_id: Optional[int] = None
    data: Optional[Any] = None
