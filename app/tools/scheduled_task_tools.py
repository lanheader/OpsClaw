# app/tools/scheduled_task_tools.py
"""
定时任务工具 - 供 Agent 在对话中创建和管理定时任务

支持：
- 创建 Cron 定时任务（如：每天 9 点执行巡检)
- 创建一次性任务(如: 2024-01-01 10:00 执行)
- 查看任务列表
- 启用/禁用任务
- 立即执行任务
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import re

from langchain_core.tools import tool

from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.scheduled_task import ScheduledTask, TaskStatus, TaskType  # type: ignore[attr-defined]
from app.services.scheduler_service import get_scheduler_service
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _parse_time_expression(time_str: str) -> Optional[Dict[str, Any]]:
    """
    解析时间表达式

    支持格式：
    - "每天9点" / "每天 9:00"
    - "每周一10点" / "每周一 10:00"
    - "每小时"
    - "2024-01-01 10:00"
    - "0 9 * * *" (cron)
    """
    time_str = time_str.strip()

    # 检查是否是 cron 表达式
    cron_pattern = r'^(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$'
    if cron_pattern:
        return {"type": "cron", "expression": time_str}

    # 中文表达式解析
    if "每天" in time_str:
        # 提取小时
        hour_match = re.search(r'(\d+)点', time_str)
        hour = hour_match.group(1) if hour_match else "9"
        return {"type": "cron", "expression": f"0 {hour} * * *"}

    if "每周" in time_str:
        # 提取星期几和小时
        week_match = re.search(r'周([一二三四五六日天])\s*(\d+)点', time_str)
        weekday = week_match.group(1) if week_match else "一"
        hour = week_match.group(2) if week_match else "9"
        # 蟥期几转数字
        weekday_map = {"日": "0", "一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6"}
        day_of_week = weekday_map.get(weekday, "1")
        return {"type": "cron", "expression": f"0 {hour} * * {day_of_week}"}

    if "每小时" in time_str:
        return {"type": "cron", "expression": "0 * * * *"}

    # 检查是否是具体时间 (一次性任务)
    datetime_pattern = r'^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})'
    if datetime_pattern:
        try:
            scheduled_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
            if scheduled_time > datetime.now():
                return {"type": "once", "time": scheduled_time}
        except ValueError:
            pass

    return None


@tool
def create_scheduled_task(
    name: str,
    task: str,
    schedule: str,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    创建定时任务

    Args:
        name: 任务名称
        task: 要执行的任务描述（如: "检查所有 Pod 的状态，生成巡检报告"）
        schedule: 调度时间，支持格式：
            - "每天9点" - 每天 9:00 执行
            - "每周一10点" - 每周一 10:00 执行
            - "每小时" - 每小时执行一次
            - "2024-01-01 10:00" - 在指定时间执行一次
            - "0 9 * * *" - 标准 cron 表达式
        description: 任务描述（可选）

    Returns:
        任务创建结果，包含任务ID和下次执行时间
    """
    try:
        # 解析时间表达式
        schedule_info = _parse_time_expression(schedule)
        if not schedule_info:
            return {"success": False, "error": f"无法解析时间表达式: {schedule}。支持的格式: 每天9点、每周一10点/每小时/2024-01-01 10:00/0 9 * * *"}

        # 获取当前用户 ID (从上下文中获取)
        # 注意： 实际使用时需要从 Agent 上下文获取 user_id
        db = next(get_db())
        try:
            scheduled_task = ScheduledTask(
                name=name,
                description=description or name,
                task_type=TaskType.CRON if schedule_info["type"] == "cron" else TaskType.ONCE,  # type: ignore[attr-defined]
                cron_expression=schedule_info.get("expression") if schedule_info["type"] == "cron" else None,
                scheduled_time=schedule_info.get("time") if schedule_info["type"] == "once" else None,
                agent_task=task,
                parameters={},
                created_by=1,  # TODO: 从上下文获取实际用户 ID
                status=TaskStatus.PENDING,
                enabled=True,
            )

            scheduler = get_scheduler_service()
            if not scheduler.create_task(db, scheduled_task):
                return {"success": False, "error": "创建任务失败"}

            # 获取下次执行时间
            next_run = scheduler.get_next_run_time(scheduled_task.id)  # type: ignore[arg-type]

            return {
                "success": True,
                "task_id": scheduled_task.id,
                "name": name,
                "schedule": schedule,
                "next_run_time": next_run.isoformat() if next_run else "未计算",
                "message": f"✅ 定时任务 '{name}' 创建成功！"
            }

        finally:
            db.close()

    except Exception as e:
        logger.exception(f"❌ 创建定时任务失败: {e}")
        return {"success": False, "error": str(e)}


@tool
def list_scheduled_tasks(
    status: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """
    查看定时任务列表

    Args:
        status: 按状态过滤 (pending/running/completed/failed/disabled)
        enabled: 按启用状态过滤

    Returns:
        任务列表
    """
    try:
        db = next(get_db())
        try:
            query = db.query(ScheduledTask)

            if status:
                query = query.filter(ScheduledTask.status == status)
            if enabled is not None:
                query = query.filter(ScheduledTask.enabled == enabled)

            tasks = query.order_by(ScheduledTask.created_at.desc()).limit(20).all()

            return [
                {
                    "id": t.id,
                    "name": t.name,
                    "description": t.description,
                    "status": t.status.value if t.status else None,
                    "enabled": t.enabled,
                    "task_type": t.task_type.value if t.task_type else None,
                    "cron_expression": t.cron_expression,
                    "scheduled_time": t.scheduled_time.isoformat() if t.scheduled_time else None,
                    "agent_task": t.agent_task,
                    "last_run_time": t.last_run_time.isoformat() if t.last_run_time else None,
                    "run_count": t.run_count,
                }
                for t in tasks
            ]
        finally:
            db.close()

    except Exception as e:
        logger.exception(f"❌ 查询定时任务失败: {e}")
        return []


@tool
def enable_scheduled_task(task_id: int) -> Dict[str, Any]:
    """
    启用定时任务

    Args:
        task_id: 任务 ID

    Returns:
        操作结果
    """
    try:
        db = next(get_db())
        try:
            scheduler = get_scheduler_service()
            if scheduler.enable_task(db, task_id):
                task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
                return {
                    "success": True,
                    "message": f"✅ 任务 '{task.name}' 已启用",  # type: ignore[union-attr]
                    "task_id": task_id
                }
            return {"success": False, "error": "启用失败"}
        finally:
            db.close()

    except Exception as e:
        logger.exception(f"❌ 启用任务失败: {e}")
        return {"success": False, "error": str(e)}


@tool
def disable_scheduled_task(task_id: int) -> Dict[str, Any]:
    """
    禁用定时任务

    Args:
        task_id: 任务 ID

    Returns:
        操作结果
    """
    try:
        db = next(get_db())
        try:
            scheduler = get_scheduler_service()
            if scheduler.disable_task(db, task_id):
                task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
                return {
                    "success": True,
                    "message": f"✅ 任务 '{task.name}' 已禁用",  # type: ignore[union-attr]
                    "task_id": task_id
                }
            return {"success": False, "error": "禁用失败"}
        finally:
            db.close()

    except Exception as e:
        logger.exception(f"❌ 禁用任务失败: {e}")
        return {"success": False, "error": str(e)}


@tool
def run_scheduled_task_now(task_id: int) -> Dict[str, Any]:
    """
    立即执行定时任务

    Args:
        task_id: 任务 ID

    Returns:
        操作结果
    """
    try:
        db = next(get_db())
        try:
            scheduler = get_scheduler_service()
            if scheduler.run_task_now(db, task_id):
                task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
                return {
                    "success": True,
                    "message": f"✅ 任务 '{task.name}' 已开始执行",  # type: ignore[union-attr]
                    "task_id": task_id
                }
            return {"success": False, "error": "执行失败"}
        finally:
            db.close()

    except Exception as e:
        logger.exception(f"❌ 执行任务失败: {e}")
        return {"success": False, "error": str(e)}


@tool
def delete_scheduled_task(task_id: int) -> Dict[str, Any]:
    """
    删除定时任务

    Args:
        task_id: 任务 ID

    Returns:
        操作结果
    """
    try:
        db = next(get_db())
        try:
            task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if not task:
                return {"success": False, "error": "任务不存在"}

            task_name = task.name
            scheduler = get_scheduler_service()

            if scheduler.delete_task(db, task_id):
                return {
                    "success": True,
                    "message": f"✅ 任务 '{task_name}' 已删除",
                    "task_id": task_id
                }
            return {"success": False, "error": "删除失败"}
        finally:
            db.close()

    except Exception as e:
        logger.exception(f"❌ 删除任务失败: {e}")
        return {"success": False, "error": str(e)}


# 导出所有工具
SCHEDULED_TASK_TOOLS = [
    create_scheduled_task,
    list_scheduled_tasks,
    enable_scheduled_task,
    disable_scheduled_task,
    run_scheduled_task_now,
    delete_scheduled_task,
]
