"""工作流域模型"""

from app.models.database import get_workflow_db, session_makers, engines, bases
from app.models.workflow.execution import WorkflowExecution
from app.models.workflow.scheduled_task import ScheduledTask, TaskType
from app.models.workflow.task_execution import TaskExecution, ExecutionStatus

# 域级数据库访问
get_db = get_workflow_db
engine = engines["workflow"]
SessionLocal = session_makers["workflow"]
Base = bases["workflow"]

__all__ = [
    "WorkflowExecution",
    "ScheduledTask",
    "TaskType",
    "TaskExecution",
    "ExecutionStatus",
    "get_db",
    "engine",
    "SessionLocal",
    "Base",
]
