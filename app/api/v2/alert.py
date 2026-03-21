"""告警 Webhook API

接收监控系统告警，触发自动诊断和处理流程
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.state import OpsState
from app.deepagents.factory import create_agent_for_session
from app.models.database import get_db
from app.models.workflow_execution import WorkflowExecution
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/alert", tags=["alert"])


class AlertWebhookPayload(BaseModel):
    """告警 Webhook 负载"""

    alert_name: str = Field(..., description="告警名称")
    severity: str = Field(default="warning", description="严重级别")
    status: str = Field(default="firing", description="告警状态")
    labels: Dict[str, str] = Field(default_factory=dict, description="告警标签")
    annotations: Dict[str, str] = Field(default_factory=dict, description="告警注释")
    starts_at: Optional[str] = Field(None, description="告警开始时间")
    ends_at: Optional[str] = Field(None, description="告警结束时间")


class AlertResponse(BaseModel):
    """告警响应"""

    task_id: str
    status: str
    message: str
    created_at: datetime


async def run_alert_workflow(task_id: str, initial_state: OpsState):
    """后台执行告警处理工作流

    Args:
        task_id: 任务ID
        initial_state: 初始状态
    """
    try:
        logger.info(f"开始执行告警处理工作流: {task_id}")

        # 创建 Agent
        agent = create_agent_for_session(
            session_id=task_id,
            enable_approval=True,
            enable_security=True,
        )

        # 执行工作流（异步，不阻塞）
        result = await agent.ainvoke(initial_state)

        logger.info(f"告警处理工作流执行完成: {task_id}, 结果: {result.get('execution_success', False)}")

    except Exception as e:
        logger.error(f"告警处理工作流执行失败: {task_id}, 错误: {e}")
        # 可以选择记录到数据库或发送通知


@router.post("/webhook", response_model=AlertResponse)
async def receive_alert(
    request: Request,
    background_tasks: BackgroundTasks
):
    """接收监控系统告警

    支持 Prometheus Alertmanager、Grafana 等监控系统的 Webhook

    Args:
        request: HTTP 请求
        background_tasks: FastAPI 后台任务

    Returns:
        AlertResponse: 告警处理任务信息
    """
    logger.info("收到告警 Webhook 请求")

    try:
        # 解析告警数据
        alert_data = await request.json()
        logger.info(f"告警数据: {alert_data}")

        # 支持 Prometheus Alertmanager 格式
        # 格式: {"alerts": [{"labels": {...}, "annotations": {...}, ...}]}
        alerts = alert_data.get("alerts", [alert_data])

        if not alerts:
            raise HTTPException(status_code=400, detail="告警数据为空")

        # 取第一个告警（简化处理）
        alert = alerts[0] if isinstance(alerts, list) else alerts

        # 提取告警信息
        alert_name = alert.get("labels", {}).get("alertname", "Unknown Alert")
        severity = alert.get("labels", {}).get("severity", "warning")
        instance = alert.get("labels", {}).get("instance", "")
        namespace = alert.get("labels", {}).get("namespace", "")
        pod = alert.get("labels", {}).get("pod", "")

        # 构造用户输入
        user_input = f"告警: {alert_name}"
        if instance:
            user_input += f" (实例: {instance})"
        if namespace and pod:
            user_input += f" (Pod: {namespace}/{pod})"

        # 生成任务ID
        task_id = f"alert_{uuid.uuid4().hex[:8]}"

        # 构造初始状态
        initial_state: OpsState = {
            "session_id": task_id,
            "user_input": user_input,
            "trigger_source": "alert",  # 告警触发源
            "intent_type": "alert",  # 直接设置为 alert 意图
            "intent_confidence": 1.0,
            "user_id": "alertmanager",
            "user_role": "system",
            "alert_data": alert,  # 保存原始告警数据
            "approval_required": True,  # 告警处理需要批准
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
            run_alert_workflow,
            task_id=task_id,
            initial_state=initial_state
        )

        logger.info(f"告警处理任务已添加到后台队列: {task_id}")

        return AlertResponse(
            task_id=task_id,
            status="pending",
            message=f"告警处理任务已创建，任务ID: {task_id}",
            created_at=datetime.now(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"接收告警失败: {e}")
        raise HTTPException(status_code=500, detail=f"接收告警失败: {str(e)}")


@router.get("/{task_id}/diagnosis")
async def get_diagnosis(task_id: str):
    """获取告警诊断报告

    Args:
        task_id: 任务ID

    Returns:
        Dict: 诊断报告
    """
    logger.info(f"查询告警诊断报告: {task_id}")

    try:
        db = next(get_db())
        execution = db.query(WorkflowExecution).filter(WorkflowExecution.task_id == task_id).first()

        if not execution:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

        diagnosis = {
            "task_id": execution.task_id,
            "status": execution.status,
            "created_at": execution.created_at.isoformat(),
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "alert_data": (
                execution.initial_state.get("alert_data") if execution.initial_state else None
            ),
            "collected_data": execution.collected_data,
            "analysis_result": execution.analysis_result,
            "remediation_plan": execution.remediation_plan,
            "final_report": execution.final_report,
        }

        logger.info(f"查询到告警诊断报告: {task_id}")
        return diagnosis

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询告警诊断报告失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询告警诊断报告失败: {str(e)}")
