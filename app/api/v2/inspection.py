"""巡检 API

提供定时巡检和手动触发巡检的接口
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.state import OpsState
from app.deepagents.factory import create_agent_for_session
from app.models.database import get_db
from app.models.user import User
from app.models.workflow_execution import WorkflowExecution
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/inspection", tags=["inspection"])


class TriggerInspectionRequest(BaseModel):
    """触发巡检请求"""

    user_id: str = Field(default="system", description="触发用户ID")
    inspection_type: str = Field(default="cluster_health", description="巡检类型")
    notification_channels: List[str] = Field(default=["feishu"], description="通知渠道")


class InspectionResponse(BaseModel):
    """巡检响应"""

    task_id: str
    status: str
    message: str
    created_at: datetime


async def run_inspection_workflow(task_id: str, initial_state: OpsState):
    """后台执行巡检工作流

    Args:
        task_id: 任务ID
        initial_state: 初始状态
    """
    try:
        logger.info(f"开始执行巡检工作流: {task_id}")

        # 创建 Agent
        agent = create_agent_for_session(
            session_id=task_id,
            enable_approval=False,
            enable_security=True,
        )

        # 执行工作流（异步，不阻塞）
        result = await agent.ainvoke(initial_state)

        logger.info(f"巡检工作流执行完成: {task_id}, 结果: {result.get('execution_success', False)}")

    except Exception as e:
        logger.error(f"巡检工作流执行失败: {task_id}, 错误: {e}")
        # 可以选择记录到数据库或发送通知


@router.post("/trigger", response_model=InspectionResponse)
async def trigger_inspection(
    request: TriggerInspectionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """手动触发巡检任务

    Args:
        request: 巡检请求参数
        background_tasks: FastAPI 后台任务
        current_user: 当前用户

    Returns:
        InspectionResponse: 巡检任务信息
    """

    logger.info(f"收到巡检触发请求: user_id={request.user_id}, type={request.inspection_type}")

    try:
        # 生成任务ID
        task_id = f"inspection_{uuid.uuid4().hex[:8]}"

        # 构造初始状态
        initial_state: OpsState = {
            "session_id": task_id,
            "user_input": f"执行{request.inspection_type}巡检",
            "trigger_source": "scheduled_task",  # 使用 scheduled_task 触发源，跳过批准
            "intent_type": "inspect",
            "intent_confidence": 1.0,
            "user_id": request.user_id,
            "user_role": "system",
            "approval_status": "approved",  # 自动批准
            "approval_required": False,  # 不需要批准
            "workflow_status": "running",
            "waiting_for_approval": False,
            "execution_success": False,
            "need_remediation": False,
            "diagnosis_round": 0,
            "max_diagnosis_rounds": 3,
            "current_command_index": 0,
            "data_sufficient": False,
            "security_check_passed": True,
            "permission_granted": True,
            "collected_data": {},
            "execution_history": [],
        }

        # 添加后台任务
        background_tasks.add_task(
            run_inspection_workflow,
            task_id=task_id,
            initial_state=initial_state
        )

        logger.info(f"巡检任务已添加到后台队列: {task_id}")

        return InspectionResponse(
            task_id=task_id,
            status="pending",
            message=f"巡检任务已创建，任务ID: {task_id}",
            created_at=datetime.now(),
        )

    except Exception as e:
        logger.error(f"触发巡检失败: {e}")
        raise HTTPException(status_code=500, detail=f"触发巡检失败: {str(e)}")


@router.get("/history")
async def get_inspection_history(limit: int = 10):
    """获取巡检历史

    Args:
        limit: 返回记录数量限制

    Returns:
        List[Dict]: 巡检历史记录
    """
    logger.info(f"查询巡检历史，限制: {limit}")

    try:
        db = next(get_db())
        executions = (
            db.query(WorkflowExecution)
            .filter(WorkflowExecution.trigger_source == "scheduled_task")
            .order_by(WorkflowExecution.created_at.desc())
            .limit(limit)
            .all()
        )

        history = []
        for execution in executions:
            history.append(
                {
                    "task_id": execution.task_id,
                    "status": execution.status,
                    "created_at": execution.created_at.isoformat(),
                    "completed_at": (
                        execution.completed_at.isoformat() if execution.completed_at else None
                    ),
                    "result": execution.result,
                }
            )

        logger.info(f"查询到 {len(history)} 条巡检历史")
        return {"history": history, "total": len(history)}

    except Exception as e:
        logger.error(f"查询巡检历史失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询巡检历史失败: {str(e)}")


@router.get("/{task_id}/report")
async def get_inspection_report(task_id: str):
    """获取巡检报告

    Args:
        task_id: 任务ID

    Returns:
        Dict: 巡检报告
    """
    logger.info(f"查询巡检报告: {task_id}")

    try:
        db = next(get_db())
        execution = db.query(WorkflowExecution).filter(WorkflowExecution.task_id == task_id).first()

        if not execution:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

        report = {
            "task_id": execution.task_id,
            "status": execution.status,
            "created_at": execution.created_at.isoformat(),
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "result": execution.result,
            "final_report": execution.final_report,
        }

        logger.info(f"查询到巡检报告: {task_id}")
        return report

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询巡检报告失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询巡检报告失败: {str(e)}")
