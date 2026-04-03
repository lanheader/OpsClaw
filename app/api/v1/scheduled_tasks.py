# app/api/v1/scheduled_tasks.py
"""
定时任务管理 API - 按需求文档规范

路由前缀: /tasks（在 main.py 中注册）
"""

from datetime import datetime, timezone as dt_timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func as sql_func

from app.models.database import get_db
from app.models.scheduled_task import ScheduledTask, TaskExecution, TaskType, ExecutionStatus
from app.models.user import User
from app.schemas.scheduled_task import (
    ScheduledTaskCreate,
    ScheduledTaskUpdate,
    ScheduledTaskResponse,
    ScheduledTaskListResponse,
    TaskExecutionResponse,
    TaskExecutionListResponse,
    TaskStatsResponse,
    TodayStats,
    TaskTypeEnum,
    ExecutionStatusEnum,
    TriggerTypeEnum,
    TaskOperationResult,
)
from app.services.scheduler_service import get_scheduler_service
from app.api.v1.auth import get_current_user
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 注意：路由前缀是 /tasks，不是 /scheduled-tasks
router = APIRouter(prefix="/tasks", tags=["tasks"])


def _task_to_response(task: ScheduledTask, include_next_run: bool = True) -> ScheduledTaskResponse:
    """转换任务模型为响应"""
    scheduler = get_scheduler_service()
    next_run = None
    if include_next_run and task.enabled:
        next_run = scheduler.get_next_run_time(task.id)  # type: ignore[arg-type]

    return ScheduledTaskResponse(
        id=task.id,  # type: ignore[arg-type]
        name=task.name,  # type: ignore[arg-type]
        description=task.description,  # type: ignore[arg-type]
        task_type=task.task_type,  # type: ignore[arg-type]
        cron_expr=task.cron_expr,  # type: ignore[arg-type]
        timezone=task.timezone or "Asia/Shanghai",  # type: ignore[arg-type]
        task_params=task.task_params,  # type: ignore[arg-type]
        enabled=task.enabled,  # type: ignore[arg-type]
        timeout=task.timeout or 600,  # type: ignore[arg-type]
        notify_on_fail=task.notify_on_fail or False,  # type: ignore[arg-type]
        notify_target=task.notify_target,  # type: ignore[arg-type]
        last_run_time=task.last_run_time,  # type: ignore[arg-type]
        last_run_status=task.last_run_status,  # type: ignore[arg-type]
        next_run_time=next_run or task.next_run_time,  # type: ignore[arg-type]
        run_count=task.run_count or 0,  # type: ignore[arg-type]
        success_count=task.success_count or 0,  # type: ignore[arg-type]
        failure_count=task.failure_count or 0,  # type: ignore[arg-type]
        created_at=task.created_at,  # type: ignore[arg-type]
        updated_at=task.updated_at,  # type: ignore[arg-type]
    )


def _execution_to_response(execution: TaskExecution, task_name: Optional[str] = None) -> TaskExecutionResponse:
    """转换执行记录为响应"""
    return TaskExecutionResponse(
        id=execution.id,  # type: ignore[arg-type]
        task_id=execution.task_id,  # type: ignore[arg-type]
        status=execution.status,  # type: ignore[arg-type]
        trigger_type=execution.trigger_type,  # type: ignore[arg-type]
        started_at=execution.started_at,  # type: ignore[arg-type]
        finished_at=execution.finished_at,  # type: ignore[arg-type]
        duration_ms=execution.duration_ms,  # type: ignore[arg-type]
        result_summary=execution.result_summary,  # type: ignore[arg-type]
        error_message=execution.error_message,  # type: ignore[arg-type]
        created_at=execution.created_at,  # type: ignore[arg-type]
        task_name=task_name,
    )


# ========== 任务管理 ==========

@router.get("", response_model=ScheduledTaskListResponse)
async def list_tasks(  # type: ignore[no-untyped-def]
    enabled: Optional[bool] = Query(None, description="按启用状态过滤"),
    task_type: Optional[TaskTypeEnum] = Query(None, description="按任务类型过滤"),
    page: int = Query(0, ge=0, description="页码，从 0 开始"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取定时任务列表"""
    query = db.query(ScheduledTask)

    if enabled is not None:
        query = query.filter(ScheduledTask.enabled == enabled)
    if task_type:
        query = query.filter(ScheduledTask.task_type == task_type.value)

    total = query.count()
    tasks = query.order_by(desc(ScheduledTask.created_at)).offset(page * size).limit(size).all()

    return ScheduledTaskListResponse(
        tasks=[_task_to_response(t) for t in tasks],
        total=total,
    )


@router.get("/stats", response_model=TaskStatsResponse)
async def get_task_stats(  # type: ignore[no-untyped-def]
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取任务统计信息"""
    # 总任务数
    total = db.query(ScheduledTask).count()
    # 已启用任务数
    enabled_count = db.query(ScheduledTask).filter(ScheduledTask.enabled == True).count()

    # 今日统计
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_executions = db.query(TaskExecution).filter(
        TaskExecution.started_at >= today_start
    ).all()

    today_total = len(today_executions)
    today_running = sum(1 for e in today_executions if e.status == ExecutionStatusEnum.RUNNING.value)
    today_success = sum(1 for e in today_executions if e.status == ExecutionStatusEnum.SUCCESS.value)
    today_failed = sum(1 for e in today_executions if e.status in [ExecutionStatusEnum.FAILED.value, ExecutionStatusEnum.TIMEOUT.value])

    return TaskStatsResponse(
        total=total,
        enabled=enabled_count,
        today_stats=TodayStats(
            total=today_total,
            running=today_running,
            success=today_success,
            failed=today_failed,
        ),
    )


@router.get("/{task_id}", response_model=ScheduledTaskResponse)
async def get_task(  # type: ignore[no-untyped-def]
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
async def create_task(  # type: ignore[no-untyped-def]
    request: ScheduledTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建定时任务"""
    scheduler = get_scheduler_service()

    task = ScheduledTask(
        name=request.name,
        description=request.description,
        task_type=request.task_type.value,
        cron_expr=request.cron_expr,
        timezone=request.timezone or "Asia/Shanghai",
        task_params=request.task_params,
        enabled=request.enabled if request.enabled is not None else True,
        timeout=request.timeout or 600,
        notify_on_fail=request.notify_on_fail or False,
        notify_target=request.notify_target,
    )

    db.add(task)
    db.commit()
    db.refresh(task)

    # 添加到调度器
    if task.enabled:
        scheduler.add_task(task)  # type: ignore[attr-defined]
        # 更新下次执行时间
        next_run = scheduler.get_next_run_time(task.id)  # type: ignore[arg-type]
        if next_run:
            task.next_run_time = next_run  # type: ignore[assignment]
            db.commit()
            db.refresh(task)

    logger.info(f"创建定时任务: {task.name} (ID: {task.id})")

    return _task_to_response(task)


@router.put("/{task_id}", response_model=ScheduledTaskResponse)
async def update_task(  # type: ignore[no-untyped-def]
    task_id: int,
    request: ScheduledTaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新定时任务"""
    scheduler = get_scheduler_service()

    task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 更新字段
    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if hasattr(task, key):
            setattr(task, key, value)

    db.commit()
    db.refresh(task)

    # 重新调度
    if task.enabled:
        scheduler.update_task(task)  # type: ignore[call-arg]
        next_run = scheduler.get_next_run_time(task.id)  # type: ignore[arg-type]
        if next_run:
            task.next_run_time = next_run  # type: ignore[assignment]
            db.commit()
            db.refresh(task)
    else:
        scheduler.remove_task(task.id)  # type: ignore[attr-defined]

    logger.info(f"更新定时任务: {task.name} (ID: {task.id})")

    return _task_to_response(task)


@router.delete("/{task_id}")
async def delete_task(  # type: ignore[no-untyped-def]
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除定时任务"""
    scheduler = get_scheduler_service()

    task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 从调度器中移除
    scheduler.remove_task(task.id)  # type: ignore[attr-defined]

    # 删除任务（级联删除执行记录）
    db.delete(task)
    db.commit()

    logger.info(f"删除定时任务: {task.name} (ID: {task_id})")

    return {"success": True, "message": "任务已删除"}


@router.post("/{task_id}/toggle", response_model=TaskOperationResult)
async def toggle_task(  # type: ignore[no-untyped-def]
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """启用/禁用任务"""
    scheduler = get_scheduler_service()

    task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 切换状态
    task.enabled = not task.enabled  # type: ignore[assignment]
    db.commit()
    db.refresh(task)

    # 更新调度器
    if task.enabled:
        scheduler.add_task(task)  # type: ignore[attr-defined]
        next_run = scheduler.get_next_run_time(task.id)  # type: ignore[arg-type]
        if next_run:
            task.next_run_time = next_run  # type: ignore[assignment]
            db.commit()
        action = "启用"
    else:
        scheduler.remove_task(task.id)  # type: ignore[attr-defined]
        action = "禁用"

    logger.info(f"{action}定时任务: {task.name} (ID: {task_id})")

    return TaskOperationResult(
        success=True,
        message=f"任务已{action}",
        task_id=task_id,
    )


@router.post("/{task_id}/run", response_model=TaskOperationResult)
async def run_task_now(  # type: ignore[no-untyped-def]
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动触发执行任务"""
    scheduler = get_scheduler_service()

    task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 检查是否有正在执行的任务
    running_execution = db.query(TaskExecution).filter(
        TaskExecution.task_id == task_id,
        TaskExecution.status == ExecutionStatusEnum.RUNNING.value
    ).first()

    if running_execution:
        raise HTTPException(status_code=400, detail="任务正在执行中，请等待完成")

    # 创建执行记录
    execution = TaskExecution(
        task_id=task_id,
        status=ExecutionStatusEnum.PENDING.value,
        trigger_type=TriggerTypeEnum.MANUAL.value,
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    # 异步执行任务
    scheduler.run_task_now(task_id, execution.id)  # type: ignore[arg-type]

    logger.info(f"手动触发任务: {task.name} (ID: {task_id})")

    return TaskOperationResult(
        success=True,
        message="任务已开始执行",
        task_id=task_id,
        data={"execution_id": execution.id},
    )


# ========== 执行记录 ==========

@router.get("/{task_id}/executions", response_model=TaskExecutionListResponse)
async def get_task_executions(  # type: ignore[no-untyped-def]
    task_id: int,
    status: Optional[ExecutionStatusEnum] = Query(None, description="按状态过滤"),
    page: int = Query(0, ge=0, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个任务的执行记录"""
    task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    query = db.query(TaskExecution).filter(TaskExecution.task_id == task_id)

    if status:
        query = query.filter(TaskExecution.status == status.value)

    total = query.count()
    executions = query.order_by(desc(TaskExecution.started_at)).offset(page * size).limit(size).all()

    return TaskExecutionListResponse(
        executions=[_execution_to_response(e, task.name) for e in executions],  # type: ignore[arg-type]
        total=total,
    )


@router.get("/executions", response_model=TaskExecutionListResponse)
async def get_all_executions(  # type: ignore[no-untyped-def]
    task_id: Optional[int] = Query(None, description="按任务ID过滤"),
    status: Optional[ExecutionStatusEnum] = Query(None, description="按状态过滤"),
    trigger_type: Optional[TriggerTypeEnum] = Query(None, description="按触发类型过滤"),
    page: int = Query(0, ge=0, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取所有执行记录"""
    query = db.query(TaskExecution)

    if task_id:
        query = query.filter(TaskExecution.task_id == task_id)
    if status:
        query = query.filter(TaskExecution.status == status.value)
    if trigger_type:
        query = query.filter(TaskExecution.trigger_type == trigger_type.value)

    total = query.count()
    executions = query.order_by(desc(TaskExecution.started_at)).offset(page * size).limit(size).all()

    # 获取任务名称映射
    task_ids = list(set(e.task_id for e in executions))
    tasks = db.query(ScheduledTask).filter(ScheduledTask.id.in_(task_ids)).all()
    task_name_map = {t.id: t.name for t in tasks}

    return TaskExecutionListResponse(
        executions=[_execution_to_response(e, task_name_map.get(e.task_id)) for e in executions],  # type: ignore[arg-type]
        total=total,
    )
