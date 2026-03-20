"""全局状态定义 - 所有Agent共享的状态"""

from typing import TypedDict, Optional, List, Dict, Any, Literal


class OpsState(TypedDict, total=False):
    """运维多智能体系统全局状态"""

    # ========== 用户信息 ==========
    user_id: str
    user_role: str  # admin, operator, viewer
    session_id: str

    # ========== 输入与意图 ==========
    user_input: str
    trigger_source: Literal["user_query", "scheduled_task", "alert", "web", "feishu", "api", "test"]
    intent_type: Optional[Literal["cluster_query", "inspect", "alert", "unknown"]]
    intent_confidence: Optional[float]
    entities: Optional[Dict[str, Any]]

    # ========== 命令规划 ==========
    planned_commands: Optional[List[Dict[str, Any]]]  # 计划执行的命令列表
    planning_reasoning: Optional[str]
    waiting_for_approval: bool
    current_command_index: int  # 当前执行到第几个命令
    diagnosis_round: int  # 诊断轮次（支持多轮数据采集）
    max_diagnosis_rounds: int  # 最大诊断轮次

    # ========== 数据采集结果 ==========
    collected_data: Dict[str, Any]  # 采集到的所有数据
    k8s_data: Optional[Dict[str, Any]]
    prometheus_metrics: Optional[Dict[str, Any]]
    log_data: Optional[List[str]]
    alert_data: Optional[Dict[str, Any]]

    # ========== 数据充足性判断 ==========
    data_sufficient: bool  # 数据是否充足
    missing_data_types: Optional[List[str]]  # 缺失的数据类型
    sufficiency_confidence: Optional[Literal["high", "medium", "low"]]
    information_gain: Optional[float]  # 继续采集的预期信息增益
    sufficiency_reason: Optional[str]
    sufficiency_next_steps: Optional[str]

    # ========== 分析结果 ==========
    analysis_result: Optional[Dict[str, Any]]
    root_cause: Optional[str]
    severity: Optional[Literal["low", "medium", "high", "critical", "info"]]
    need_remediation: bool  # 是否需要修复
    issue_type: Optional[str]
    business_impact: Optional[str]
    urgency: Optional[str]
    analysis_confidence: Optional[Literal["high", "medium", "low"]]

    # ========== 修复方案 ==========
    remediation_plan: Optional[Dict[str, Any]]
    remediation_commands: Optional[List[Dict[str, Any]]]

    # ========== 安全审核 ==========
    security_check_passed: bool
    risk_level: Optional[Literal["low", "medium", "high"]]
    dangerous_operations: Optional[List[str]]
    security_warnings: Optional[List[str]]

    # ========== 权限校验 ==========
    permission_granted: bool
    permission_check_result: Optional[Dict[str, Any]]

    # ========== 用户审批 ==========
    approval_required: bool
    needs_approval: Optional[bool]  # 兼容旧调用方/旧测试
    approval_status: Optional[Literal["pending", "approved", "rejected"]]
    approval_message: Optional[str]

    # ========== 会话状态（新增）==========
    has_pending_approval: bool  # 是否有待批准的操作
    is_approval_response: bool  # 用户回复是否是确认/拒绝
    approval_decision: Optional[Literal["approved", "rejected"]]  # 批准决定
    conversation_history: Optional[List[Dict[str, str]]]  # 对话历史

    # ========== 执行结果 ==========
    execution_result: Optional[Dict[str, Any]]
    execution_success: bool
    execution_logs: Optional[List[str]]

    # ========== 最终报告 ==========
    final_report: Optional[str]
    formatted_response: Optional[str]
    response_format: Optional[str]
    report_type: Optional[str]
    report_title: Optional[str]
    report_metadata: Optional[Dict[str, Any]]
    lessons_learned: Optional[List[str]]

    # ========== 流程控制 ==========
    _route_target: Optional[str]  # 智能路由阶段的临时目标节点
    next_node: Optional[str]  # 下一个要执行的节点
    workflow_status: Literal["running", "waiting_approval", "completed", "failed", "paused"]
    error_message: Optional[str]

    # ========== 审计追踪 ==========
    execution_history: List[Dict[str, Any]]  # 执行历史记录
    timestamp: str
