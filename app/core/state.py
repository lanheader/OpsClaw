"""全局状态定义 - 运维多智能体系统状态"""

from typing import TypedDict, Optional, List, Dict, Any, Literal


class OpsState(TypedDict, total=False):
    """运维多智能体系统全局状态"""

    # ========== 用户信息 ==========
    user_id: str
    user_role: str
    session_id: str

    # ========== 输入与意图 ==========
    user_input: str
    trigger_source: Literal["user_query", "scheduled_task", "alert", "web", "feishu", "api", "test"]
    intent_type: Optional[Literal["cluster_query", "inspect", "alert", "unknown"]]
    intent_confidence: Optional[float]

    # ========== 命令规划 ==========
    waiting_for_approval: bool
    current_command_index: int
    diagnosis_round: int
    max_diagnosis_rounds: int

    # ========== 数据采集结果 ==========
    collected_data: Dict[str, Any]
    alert_data: Optional[Dict[str, Any]]

    # ========== 数据充足性判断 ==========
    data_sufficient: bool

    # ========== 分析结果 ==========
    analysis_result: Optional[Dict[str, Any]]
    root_cause: Optional[str]
    severity: Optional[Literal["low", "medium", "high", "critical", "info"]]
    need_remediation: bool

    # ========== 修复方案 ==========
    remediation_plan: Optional[Dict[str, Any]]

    # ========== 安全审核 ==========
    security_check_passed: bool
    risk_level: Optional[Literal["low", "medium", "high"]]

    # ========== 权限校验 ==========
    permission_granted: bool

    # ========== 用户审批 ==========
    approval_required: bool
    approval_status: Optional[Literal["pending", "approved", "rejected"]]
    approval_message: Optional[str]

    # ========== 会话状态 ==========
    is_approval_response: bool
    approval_decision: Optional[Literal["approved", "rejected"]]

    # ========== 执行结果 ==========
    execution_success: bool

    # ========== 最终报告 ==========
    final_report: Optional[str]

    # ========== 流程控制 ==========
    workflow_status: Literal["running", "waiting_approval", "completed", "failed", "paused"]
    error_message: Optional[str]

    # ========== 审计追踪 ==========
    execution_history: List[Dict[str, Any]]
