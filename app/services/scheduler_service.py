# app/services/scheduler_service.py
"""
定时任务调度服务

使用 APScheduler 进行任务调度，支持：
1. Cron 表达式
2. 一次性定时任务
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from functools import partial

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.base import JobLookupError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.database import get_db
from app.models.scheduled_task import ScheduledTask, TaskExecutionLog, TaskStatus, TaskType
from app.services.agent_chat_service import get_agent_chat_service, ChatRequest, MessageChannel
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SchedulerService:
    """定时任务调度服务"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._running = False
        self.settings = get_settings()

    def start(self):
        """启动调度器"""
        if not self._running:
            self.scheduler.start()
            self._running = True
            logger.info("✅ 定时任务调度器已启动")

            # 加载所有启用的任务
            self._load_enabled_tasks()

    def shutdown(self):
        """关闭调度器"""
        if self._running:
            self.scheduler.shutdown(wait=False)
            self._running = False
            logger.info("🛑 定时任务调度器已关闭")

    def _load_enabled_tasks(self):
        """加载所有启用的任务"""
        db = next(get_db())
        try:
            tasks = db.query(ScheduledTask).filter(
                ScheduledTask.enabled == True,
                ScheduledTask.status.in_([TaskStatus.PENDING, TaskStatus.COMPLETED])
            ).all()

            for task in tasks:
                self._add_job(task)
                logger.info(f"📅 加载任务: {task.name} (ID: {task.id})")

        except Exception as e:
            logger.exception(f"❌ 加载任务失败: {e}")
        finally:
            db.close()

    def _add_job(self, task: ScheduledTask) -> bool:
        """添加任务到调度器"""
        try:
            job_id = f"task_{task.id}"

            # 如果任务已存在，先删除
            try:
                self.scheduler.remove_job(job_id)
            except JobLookupError:
                pass

            # 根据任务类型创建触发器
            if task.task_type == TaskType.CRON:
                if not task.cron_expression:
                    logger.error(f"❌ Cron 任务缺少表达式: {task.id}")
                    return False

                # 解析 cron 表达式（支持 5 字段标准格式）
                parts = task.cron_expression.split()
                if len(parts) != 5:
                    logger.error(f"❌ 无效的 Cron 表达式: {task.cron_expression}")
                    return False

                trigger = CronTrigger(
                    minute=parts[0],
                    hour=parts[1],
                    day=parts[2],
                    month=parts[3],
                    day_of_week=parts[4],
                )

            elif task.task_type == TaskType.ONCE:
                if not task.scheduled_time:
                    logger.error(f"❌ 一次性任务缺少执行时间: {task.id}")
                    return False

                trigger = DateTrigger(run_date=task.scheduled_time)

            else:
                logger.error(f"❌ 未知的任务类型: {task.task_type}")
                return False

            # 添加任务
            self.scheduler.add_job(
                self._execute_task,
                trigger=trigger,
                id=job_id,
                args=[task.id],
                name=task.name,
                replace_existing=True,
            )

            # 更新下次执行时间
            job = self.scheduler.get_job(job_id)
            if job:
                db = next(get_db())
                try:
                    db_task = db.query(ScheduledTask).filter(ScheduledTask.id == task.id).first()
                    if db_task:
                        db_task.next_run_time = job.next_run_time
                        db.commit()
                finally:
                    db.close()

            logger.info(f"✅ 任务已调度: {task.name}, 下次执行: {job.next_run_time if job else 'N/A'}")
            return True

        except Exception as e:
            logger.exception(f"❌ 添加任务失败: {e}")
            return False

    async def _execute_task(self, task_id: int):
        """执行任务"""
        db = next(get_db())
        log = None

        try:
            # 获取任务
            task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if not task:
                logger.error(f"❌ 任务不存在: {task_id}")
                return

            if not task.enabled:
                logger.info(f"⏭️ 任务已禁用，跳过执行: {task.name}")
                return

            logger.info(f"🚀 开始执行任务: {task.name} (ID: {task_id})")

            # 更新任务状态
            task.status = TaskStatus.RUNNING
            task.last_run_time = datetime.now()
            db.commit()

            # 创建执行日志
            log = TaskExecutionLog(
                task_id=task_id,
                started_at=datetime.now(),
                status="running",
            )
            db.add(log)
            db.commit()
            db.refresh(log)

            # 执行 Agent 任务
            session_id = f"scheduled_{task_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

            request = ChatRequest(
                session_id=session_id,
                user_id=task.created_by,
                content=task.agent_task,
                channel=MessageChannel.WEB,
                user_permissions=[],
            )

            service = get_agent_chat_service()
            response = await service.process_message(request)

            # 更新执行结果
            log.finished_at = datetime.now()
            log.duration_seconds = int((log.finished_at - log.started_at).total_seconds())
            log.session_id = session_id

            if response.workflow_status == "completed":
                log.status = "success"
                log.result = response.reply
                task.last_run_status = "success"
                task.success_count += 1
            else:
                log.status = "failed"
                log.error_message = response.reply
                task.last_run_status = "failed"
                task.failure_count += 1

            task.last_run_result = response.reply[:500] if response.reply else None
            task.run_count += 1
            task.status = TaskStatus.COMPLETED

            # 更新下次执行时间（仅 Cron 任务）
            if task.task_type == TaskType.CRON:
                job = self.scheduler.get_job(f"task_{task_id}")
                if job:
                    task.next_run_time = job.next_run_time
            else:
                # 一次性任务执行后禁用
                task.enabled = False
                task.status = TaskStatus.COMPLETED

            db.commit()
            logger.info(f"✅ 任务执行完成: {task.name}, 状态: {log.status}")

        except Exception as e:
            logger.exception(f"❌ 任务执行失败: {e}")

            # 更新失败状态
            if log:
                log.status = "error"
                log.error_message = str(e)
                log.finished_at = datetime.now()
                log.duration_seconds = int((log.finished_at - log.started_at).total_seconds())

            try:
                task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
                if task:
                    task.status = TaskStatus.FAILED
                    task.last_run_status = "error"
                    task.failure_count += 1
                    db.commit()
            except Exception as db_error:
                logger.error(f"⚠️ 更新任务失败状态时出错 (task_id={task_id}): {db_error}")

        finally:
            db.close()

    # ========== 公共 API ==========

    def create_task(self, db: Session, task: ScheduledTask) -> bool:
        """创建并调度新任务"""
        try:
            db.add(task)
            db.commit()
            db.refresh(task)

            if task.enabled:
                return self._add_job(task)
            return True

        except Exception as e:
            logger.exception(f"❌ 创建任务失败: {e}")
            return False

    def update_task(self, db: Session, task_id: int, updates: Dict[str, Any]) -> Optional[ScheduledTask]:
        """更新任务"""
        try:
            task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if not task:
                return None

            for key, value in updates.items():
                if hasattr(task, key):
                    setattr(task, key, value)

            db.commit()
            db.refresh(task)

            # 重新调度
            if task.enabled:
                self._add_job(task)
            else:
                try:
                    self.scheduler.remove_job(f"task_{task_id}")
                except JobLookupError:
                    pass

            return task

        except Exception as e:
            logger.exception(f"❌ 更新任务失败: {e}")
            return None

    def delete_task(self, db: Session, task_id: int) -> bool:
        """删除任务"""
        try:
            task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if not task:
                return False

            # 从调度器中移除
            try:
                self.scheduler.remove_job(f"task_{task_id}")
            except JobLookupError:
                pass

            db.delete(task)
            db.commit()
            return True

        except Exception as e:
            logger.exception(f"❌ 删除任务失败: {e}")
            return False

    def enable_task(self, db: Session, task_id: int) -> bool:
        """启用任务"""
        return self.update_task(db, task_id, {"enabled": True, "status": TaskStatus.PENDING}) is not None

    def disable_task(self, db: Session, task_id: int) -> bool:
        """禁用任务"""
        return self.update_task(db, task_id, {"enabled": False, "status": TaskStatus.DISABLED}) is not None

    def run_task_now(self, db: Session, task_id: int) -> bool:
        """立即执行任务"""
        try:
            task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if not task:
                return False

            # 异步执行
            asyncio.create_task(self._execute_task(task_id))
            return True

        except Exception as e:
            logger.exception(f"❌ 立即执行任务失败: {e}")
            return False

    def get_next_run_time(self, task_id: int) -> Optional[datetime]:
        """获取下次执行时间"""
        try:
            job = self.scheduler.get_job(f"task_{task_id}")
            return job.next_run_time if job else None
        except Exception as e:
            logger.warning(f"⚠️ 获取下次执行时间失败 (task_id={task_id}): {e}")
            return None


# 单例
_scheduler_service: Optional[SchedulerService] = None


def get_scheduler_service() -> SchedulerService:
    """获取调度服务单例"""
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service
