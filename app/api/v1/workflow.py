# app/api/v1/workflow.py
"""工作流 API 端点 - DeepAgents 架构"""

from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.deepagents.factory import create_agent_for_session
from app.core.state import OpsState
from app.models.database import get_db
from app.models.user import User
from app.core.deps import get_current_user

router = APIRouter(prefix="/workflow", tags=["workflow"])


class WorkflowExecuteRequest(BaseModel):
    """执行新工作流的请求"""

    user_input: str = Field(
        ...,
        description="用户输入",
        examples=["查询当前集群中所有Pod的状态", "应用响应很慢，帮我诊断一下"],
    )
    user_id: str = Field(default="default_user", description="用户ID")
    user_role: str = Field(
        default="admin", description="用户角色", examples=["admin", "operator", "viewer"]
    )
    trigger_source: str = Field(
        default="user_query",
        description="触发源",
        examples=["user_query", "scheduled_task", "alert"],
    )


class WorkflowExecuteResponse(BaseModel):
    """工作流执行的响应"""

    session_id: str
    user_input: str
    intent_type: Optional[str]
    workflow_status: str
    diagnosis_round: int
    need_remediation: bool
    execution_success: bool
    approval_message: Optional[str] = None  # 命令规划消息
    final_report: Optional[str]
    error_message: Optional[str]


class WorkflowStatusResponse(BaseModel):
    """工作流状态查询的响应"""

    task_id: str
    status: str
    current_step: str
    health_status: Optional[str] = None
    needs_approval: bool
    approval_status: Optional[str] = None
    success: Optional[bool] = None
    messages: list


@router.post("/execute", response_model=WorkflowExecuteResponse)
async def execute_workflow(  # type: ignore[no-untyped-def]
    request: WorkflowExecuteRequest, current_user: User = Depends(get_current_user)
):
    """
    执行新的 DeepAgents 工作流

    此端点使用指定的参数启动新的工作流执行
    工作流将通过 DeepAgents 主智能体同步执行

    Returns:
        WorkflowExecuteResponse with execution result
    """
    try:
        # 1. 创建 Agent（v3.0 单例模式，异步）
        agent = await create_agent_for_session(  # type: ignore[call-arg]
            session_id=f"workflow_{current_user.id}_{request.user_input[:20]}",
            enable_approval=True,
            enable_security=True,
        )

        # 2. 初始化状态
        session_id = f"workflow_{current_user.id}"
        state: OpsState = {
            "user_id": str(current_user.id),
            "user_role": "admin" if current_user.is_superuser else "user",
            "session_id": session_id,
            "user_input": request.user_input,
            "trigger_source": request.trigger_source,  # type: ignore[typeddict-item]
            "workflow_status": "running",
            "waiting_for_approval": False,
            "approval_required": False,
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

        # 【重要】LangGraph checkpointer 需要 config 中的 thread_id
        config = {
            "configurable": {
                "thread_id": session_id
            }
        }

        # 3. 执行 Agent (同步)
        result = await agent.ainvoke(state, config=config)

        # 4. 返回结果
        return WorkflowExecuteResponse(
            session_id=result.get("session_id", ""),
            user_input=result.get("user_input", ""),
            intent_type=result.get("intent_type"),
            workflow_status=result.get("workflow_status", ""),
            diagnosis_round=result.get("diagnosis_round", 0),
            need_remediation=result.get("need_remediation", False),
            execution_success=result.get("execution_success", False),
            approval_message=result.get("approval_message"),
            final_report=result.get("final_report"),
            error_message=result.get("error_message"),
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Workflow execution failed: {str(e)}",
        )


@router.get("/health")
async def health_check():  # type: ignore[no-untyped-def]
    """健康检查"""
    return {"status": "ok", "message": "Workflow API is running"}
