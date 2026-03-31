# app/api/v1/scheduled_tasks.py
"""
定时任务管理 API
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.database import get_db
from app.models.scheduled_task import ScheduledTask, TaskExecutionLog, TaskStatus, TaskType
from app.models.user import User
from app.schemas.scheduled_task import (
    ScheduledTaskCreate,
    ScheduledTaskUpdate,
    ScheduledTaskResponse,
    ScheduledTaskListResponse,
    TaskExecutionLogResponse,
    TaskExecutionLogListResponse,
    TaskTypeEnum,
    TaskStatusEnum,
)
from app.services.scheduler_service import get_scheduler_service
from app.api.v1.auth import get_current_user
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/scheduled-tasks", tags=["scheduled-tasks"])


def _task_to_response(task: ScheduledTask) -> ScheduledTaskResponse:
    """转换任务模型为响应"""
    scheduler = get_scheduler_service()
    next_run = scheduler.get_next_run_time(task.id)

    return ScheduledTaskResponse(
        id=task.id,
        name=task.name,
        description=task.description,
        task_type=task.task_type.value if task.task_type else "cron",
        cron_expression=task.cron_expression,
        scheduled_time=task.scheduled_time,
        agent_task=task.agent_task,
        parameters=task.parameters or {},
        status=task.status.value if task.status else "pending",
        enabled=task.enabled,
        last_run_time=task.last_run_time,
        last_run_status=task.last_run_status,
        last_run_result=task.last_run_result,
        next_run_time=next_run or task.next_run_time,
        run_count=task.run_count,
        success_count=task.success_count,
        failure_count=task.failure_count,
        created_by=task.created_by,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


# ========== 任务 CRUD ==========

@router.get("", response_model=ScheduledTaskListResponse)
async def list_tasks(
    status: Optional[TaskStatusEnum] = Query(None, description="按状态过滤"),
    task_type: Optional[TaskTypeEnum] = Query(None, description="按类型过滤"),
    enabled: Optional[bool] = Query(None, description="按启用状态过滤"),
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取定时任务列表"""
    query = db.query(ScheduledTask)

    if status:
        query = query.filter(ScheduledTask.status == status.value)
    if task_type:
        query = query.filter(ScheduledTask.task_type == task_type.value)
    if enabled is not None:
        query = query.filter(ScheduledTask.enabled == enabled)

    total = query.count()
    tasks = query.order_by(desc(ScheduledTask.created_at)).offset(page * size).limit(size).all()

    return ScheduledTaskListResponse(
        tasks=[_task_to_response(t) for t in tasks],
        total=total,
    )


@router.get("/{task_id}", response_model=ScheduledTaskResponse)
async def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个任务详情"""
    task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return _task_to_response(task)


@router.post("", response_model=ScheduledTaskResponse)
async def create_task(
    request: ScheduledTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建定时任务"""
    scheduler = get_scheduler_service()

    task = ScheduledTask(
        name=request.name,
        description=request.description,
        task_type=TaskType.CRON if request.task_type == TaskTypeEnum.CRON else TaskType.ONCE,
        cron_expression=request.cron_expression,
        scheduled_time=request.scheduled_time,
        agent_task=request.agent_task,
        parameters=request.parameters,
        created_by=current_user.id,
        status=TaskStatus.PENDING,
        enabled=True,
    )

    if not scheduler.create_task(db, task):
        raise HTTPException(status_code=500, detail="创建任务失败")

    return _task_to_response(task)


@router.put("/{task_id}", response_model=ScheduledTaskResponse)
async def update_task(
    task_id: int,
    request: ScheduledTaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新定时任务"""
    scheduler = get_scheduler_service()

    updates = request.model_dump(exclude_unset=True)

    # 转换枚举类型
    if "task_type" in updates:
        updates["task_type"] = TaskType.CRON if updates["task_type"] == TaskTypeEnum.CRON else TaskType.ONCE

    task = scheduler.update_task(db, task_id, updates)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或更新失败")

    return _task_to_response(task)


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除定时任务"""
    scheduler = get_scheduler_service()

    if not scheduler.delete_task(db, task_id):
        raise HTTPException(status_code=404, detail="任务不存在或删除失败")

    return {"success": True, "message": "任务已删除"}


# ========== 任务操作 ==========

@router.post("/{task_id}/enable")
async def enable_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """启用任务"""
    scheduler = get_scheduler_service()

    if not scheduler.enable_task(db, task_id):
        raise HTTPException(status_code=404, detail="任务不存在或启用失败")

    return {"success": True, "message": "任务已启用"}


@router.post("/{task_id}/disable")
async def disable_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """禁用任务"""
    scheduler = get_scheduler_service()

    if not scheduler.disable_task(db, task_id):
        raise HTTPException(status_code=404, detail="任务不存在或禁用失败")

    return {"success": True, "message": "任务已禁用"}


@router.post("/{task_id}/run")
async def run_task_now(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """立即执行任务"""
    scheduler = get_scheduler_service()

    if not scheduler.run_task_now(db, task_id):
        raise HTTPException(status_code=404, detail="任务不存在或执行失败")

    return {"success": True, "message": "任务已开始执行"}


# ========== 执行日志 ==========

@router.get("/{task_id}/logs", response_model=TaskExecutionLogListResponse)
async def get_task_logs(
    task_id: int,
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取任务执行日志"""
    # 验证任务存在
    task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    query = db.query(TaskExecutionLog).filter(TaskExecutionLog.task_id == task_id)
    total = query.count()
    logs = query.order_by(desc(TaskExecutionLog.started_at)).offset(page * size).limit(size).all()

    return TaskExecutionLogListResponse(
        logs=[
            TaskExecutionLogResponse(
                id=log.id,
                task_id=log.task_id,
                started_at=log.started_at,
                finished_at=log.finished_at,
                duration_seconds=log.duration_seconds,
                status=log.status,
                result=log.result,
                error_message=log.error_message,
                session_id=log.session_id,
            )
            for log in logs
        ],
        total=total,
    )


# ========== 统计信息 ==========

@router.get("/stats/summary")
async def get_task_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取任务统计信息"""
    total = db.query(ScheduledTask).count()
    enabled = db.query(ScheduledTask).filter(ScheduledTask.enabled == True).count()
    running = db.query(ScheduledTask).filter(ScheduledTask.status == TaskStatus.RUNNING).count()
    completed = db.query(ScheduledTask).filter(ScheduledTask.status == TaskStatus.COMPLETED).count()
    failed = db.query(ScheduledTask).filter(ScheduledTask.status == TaskStatus.FAILED).count()

    return {
        "total": total,
        "enabled": enabled,
        "disabled": total - enabled,
        "running": running,
        "completed": completed,
        "failed": failed,
    }
