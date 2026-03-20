# app/core/scheduler.py
"""任务调度器"""

from typing import Callable, List, Dict, Any, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TaskScheduler:
    """基于 APScheduler 的异步任务调度器"""

    def __init__(self, db_url: Optional[str] = None):
        """
        初始化任务调度器

        Args:
            db_url: 数据库 URL，用于持久化任务。如果为 None，使用内存存储（不持久化）
        """
        # 配置任务存储
        if db_url and db_url != "sqlite:///:memory:":
            # 使用 SQLAlchemy 持久化存储
            jobstores = {"default": SQLAlchemyJobStore(url=db_url)}
        else:
            # 使用内存存储（测试或非持久化场景）
            jobstores = {"default": MemoryJobStore()}

        # 配置执行器
        executors = {"default": AsyncIOExecutor()}

        # 任务默认配置
        job_defaults = {
            "coalesce": False,  # 不合并错过的任务
            "max_instances": 3,  # 同一任务最大并发数
            "misfire_grace_time": 60,  # 错过执行的容忍时间（秒）
        }

        # 创建调度器
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores, executors=executors, job_defaults=job_defaults
        )

        logger.info("TaskScheduler initialized")

    def start(self):
        """启动调度器"""
        if self.scheduler.state == 0:  # STATE_STOPPED
            self.scheduler.start()
            logger.info("TaskScheduler started")
        else:
            logger.warning("TaskScheduler already running")

    def shutdown(self, wait: bool = True):
        """
        停止调度器

        Args:
            wait: 是否等待正在执行的任务完成
        """
        if self.scheduler.state == 1:  # STATE_RUNNING
            self.scheduler.shutdown(wait=wait)
            logger.info("TaskScheduler stopped")
        else:
            logger.warning("TaskScheduler not running")

    def add_interval_job(
        self, func: Callable, seconds: int, job_id: str, **kwargs
    ) -> Optional[Any]:
        """
        添加间隔任务

        Args:
            func: 要执行的函数
            seconds: 间隔秒数
            job_id: 任务唯一标识
            **kwargs: 传递给函数的额外参数

        Returns:
            Job 对象或 None（如果添加失败）
        """
        try:
            job = self.scheduler.add_job(
                func=func,
                trigger=IntervalTrigger(seconds=seconds),
                id=job_id,
                replace_existing=True,
                kwargs=kwargs,
            )
            logger.info(f"Added interval job: {job_id} (every {seconds}s)")
            return job
        except Exception as e:
            logger.error(f"Failed to add interval job {job_id}: {e}")
            return None

    def add_cron_job(self, func: Callable, job_id: str, **kwargs) -> Optional[Any]:
        """
        添加 cron 任务

        Args:
            func: 要执行的函数
            job_id: 任务唯一标识
            **kwargs: 可以包含:
                - cron 参数: minute, hour, day, month, day_of_week, week, year
                - 函数参数: 其他任何参数都会传递给 func

        Returns:
            Job 对象或 None（如果添加失败）
        """
        try:
            # 分离 cron 参数和函数参数
            cron_params = {}
            func_params = {}

            cron_fields = {
                "minute",
                "hour",
                "day",
                "month",
                "day_of_week",
                "week",
                "year",
                "second",
            }

            for key, value in kwargs.items():
                if key in cron_fields:
                    cron_params[key] = value
                else:
                    func_params[key] = value

            job = self.scheduler.add_job(
                func=func,
                trigger=CronTrigger(**cron_params) if cron_params else CronTrigger(),
                id=job_id,
                replace_existing=True,
                kwargs=func_params,
            )
            logger.info(f"Added cron job: {job_id} with schedule {cron_params}")
            return job
        except Exception as e:
            logger.error(f"Failed to add cron job {job_id}: {e}")
            return None

    def remove_job(self, job_id: str) -> bool:
        """
        移除任务

        Args:
            job_id: 任务唯一标识

        Returns:
            是否移除成功
        """
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed job: {job_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to remove job {job_id}: {e}")
            return False

    def list_jobs(self) -> List[Dict[str, Any]]:
        """
        列出所有任务

        Returns:
            任务信息列表
        """
        jobs = []
        for job in self.scheduler.get_jobs():
            job_info = {
                "id": job.id,
                "trigger": str(job.trigger),
                "next_run_time": str(job.next_run_time) if job.next_run_time else None,
            }
            jobs.append(job_info)

        return jobs
