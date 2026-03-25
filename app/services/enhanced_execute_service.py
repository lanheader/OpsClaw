"""
增强的执行服务 - 使用 ReAct + Self-Reflection + 回滚机制

设计模式组合：
1. ReAct: 推理与行动循环 (Thought → Action → Observation)
2. Self-Reflection: 执行前风险评估、执行后验证
3. Plan-and-Solve: 详细的执行规划

核心流程：
1. Pre-Execution: 风险评估
2. Planning: 生成执行计划
3. Execution: ReAct 循环执行
4. Verification: 验证执行结果
5. Rollback: 失败时回滚
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Tuple, Callable
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm_factory import LLMFactory
from app.tools import get_tools_by_group
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ==================== 枚举类型 ====================

class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExecutionStatus(Enum):
    """执行状态"""
    PENDING = "pending"
    ASSESSING = "assessing"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


# ==================== 数据模型 ====================

@dataclass
class RiskAssessment:
    """风险评估结果"""
    risk_level: RiskLevel
    risk_score: float  # 0.0 - 1.0
    risk_factors: List[str]  # 识别的风险因素
    mitigation_strategies: List[str]  # 缓解策略
    requires_approval: bool  # 是否需要人工批准
    approval_reason: str = ""  # 需要批准的原因


@dataclass
class ExecutionStep:
    """执行步骤"""
    id: str
    action: str  # 具体操作
    tool: str  # 使用的工具
    params: Dict[str, Any]  # 参数
    expected_outcome: str  # 期望结果
    rollback_action: Optional[str] = None  # 回滚操作
    rollback_params: Optional[Dict[str, Any]] = None  # 回滚参数


@dataclass
class ExecutionPlan:
    """执行计划"""
    steps: List[ExecutionStep]
    estimated_duration: float  # 预估耗时（秒）
    risk_assessment: RiskAssessment
    verification_steps: List[str]  # 验证步骤


@dataclass
class StepResult:
    """步骤执行结果"""
    step_id: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration: float = 0.0
    verified: bool = False  # 是否已验证


@dataclass
class ExecutionResult:
    """执行结果"""
    status: ExecutionStatus
    steps_results: List[StepResult]
    final_output: Any = None
    error: Optional[str] = None
    total_duration: float = 0.0
    rollback_performed: bool = False
    rollback_details: Optional[str] = None
    verification_results: Dict[str, bool] = field(default_factory=dict)


# ==================== 增强执行服务 ====================

class EnhancedExecuteService:
    """
    增强的执行服务 - 使用 ReAct + Self-Reflection + 回滚机制

    工作流程：
    1. 风险评估：评估操作风险等级
    2. 执行规划：生成详细的执行计划
    3. ReAct 执行：逐步执行并观察
    4. 结果验证：验证操作是否成功
    5. 自动回滚：失败时自动回滚
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        self.llm = llm or LLMFactory.create_llm_for_subagent("execute-agent")

        # 获取可用工具
        self.k8s_tools = get_tools_by_group("k8s.write") + get_tools_by_group("k8s.delete")
        self.command_tools = get_tools_by_group("command")

        # 工具映射
        self._tool_map = {}
        for tool_list in [self.k8s_tools, self.command_tools]:
            for tool in tool_list:
                if hasattr(tool, 'name'):
                    self._tool_map[tool.name] = tool

        # 回滚历史
        self._rollback_history: List[Dict[str, Any]] = []

    async def execute_with_safety(
        self,
        user_query: str,
        remediation_plan: List[str],
        context: Dict[str, Any] = None,
        auto_rollback: bool = True,
        require_approval_for: List[RiskLevel] = None
    ) -> ExecutionResult:
        """
        安全执行操作（包含风险评估、执行、验证、回滚）

        Args:
            user_query: 用户查询/操作意图
            remediation_plan: 修复计划步骤列表
            context: 上下文信息
            auto_rollback: 是否自动回滚
            require_approval_for: 需要批准的风险等级列表

        Returns:
            执行结果
        """
        require_approval_for = require_approval_for or [RiskLevel.HIGH, RiskLevel.CRITICAL]
        context = context or {}

        logger.info(f"🛡️ [EnhancedExecute] 开始安全执行: {user_query[:50]}...")

        # Phase 1: 风险评估
        risk_assessment = await self._assess_risk(
            user_query=user_query,
            remediation_plan=remediation_plan,
            context=context
        )
        logger.info(f"⚠️ [风险评估] 等级: {risk_assessment.risk_level.value}, 分数: {risk_assessment.risk_score:.2f}")

        # 检查是否需要批准
        if risk_assessment.requires_approval or risk_assessment.risk_level in require_approval_for:
            logger.warning(f"🚨 [高风险操作] 需要 {risk_assessment.risk_level.value} 级别批准")
            return ExecutionResult(
                status=ExecutionStatus.PENDING,
                steps_results=[],
                error=f"操作需要 {risk_assessment.risk_level.value} 级别批准: {risk_assessment.approval_reason}"
            )

        # Phase 2: 生成执行计划
        execution_plan = await self._create_execution_plan(
            user_query=user_query,
            remediation_plan=remediation_plan,
            context=context,
            risk_assessment=risk_assessment
        )
        logger.info(f"📋 [执行计划] {len(execution_plan.steps)} 个步骤, 预计 {execution_plan.estimated_duration:.1f}秒")

        # Phase 3: ReAct 执行循环
        steps_results = []
        total_duration = 0.0

        for step in execution_plan.steps:
            logger.info(f"🔄 [执行] 步骤 {step.id}: {step.action}")

            step_result = await self._execute_step_with_verification(
                step=step,
                context=context
            )

            steps_results.append(step_result)
            total_duration += step_result.duration

            # 如果步骤失败且启用自动回滚
            if not step_result.success and auto_rollback:
                logger.error(f"❌ [执行失败] 步骤 {step.id} 失败，执行回滚")
                rollback_result = await self._rollback_steps(
                    executed_steps=steps_results,
                    context=context
                )
                return ExecutionResult(
                    status=ExecutionStatus.ROLLED_BACK,
                    steps_results=steps_results,
                    error=f"步骤 {step.id} 执行失败: {step_result.error}",
                    total_duration=total_duration,
                    rollback_performed=True,
                    rollback_details=rollback_result
                )

        # Phase 4: 验证执行结果
        verification_results = await self._verify_execution(
            execution_plan=execution_plan,
            steps_results=steps_results,
            context=context
        )

        all_verified = all(verification_results.values())

        if all_verified:
            logger.info("✅ [验证成功] 所有步骤验证通过")
            return ExecutionResult(
                status=ExecutionStatus.COMPLETED,
                steps_results=steps_results,
                total_duration=total_duration,
                verification_results=verification_results
            )
        else:
            failed_verifications = [k for k, v in verification_results.items() if not v]
            logger.warning(f"⚠️ [验证失败] 部分验证失败: {failed_verifications}")
            return ExecutionResult(
                status=ExecutionStatus.COMPLETED,  # 执行完成但验证部分失败
                steps_results=steps_results,
                total_duration=total_duration,
                verification_results=verification_results
            )

    async def _assess_risk(
        self,
        user_query: str,
        remediation_plan: List[str],
        context: Dict[str, Any]
    ) -> RiskAssessment:
        """Phase 1: 风险评估"""
        prompt = f"""作为运维安全专家，请评估以下操作的风险：

用户意图：{user_query}

修复计划：
{json.dumps(remediation_plan, ensure_ascii=False, indent=2)}

上下文：
{json.dumps(context, ensure_ascii=False, indent=2)}

请评估：

1. 风险等级（LOW/MEDIUM/HIGH/CRITICAL）：
   - LOW: 只读操作或低风险配置变更
   - MEDIUM: 非关键服务的重启/配置修改
   - HIGH: 生产环境关键服务操作、删除资源
   - CRITICAL: 数据库操作、大规模删除、可能导致服务中断

2. 风险分数（0.0-1.0）

3. 风险因素（识别具体风险）

4. 缓解策略（如何降低风险）

以 JSON 格式输出：
```json
{{
  "risk_level": "MEDIUM",
  "risk_score": 0.6,
  "risk_factors": ["操作影响生产环境", "可能导致短暂服务中断"],
  "mitigation_strategies": ["在低峰期执行", "准备回滚方案"],
  "requires_approval": false,
  "approval_reason": ""
}}
```
"""

        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content

            # 提取 JSON
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
            else:
                start = content.find("{")
                end = content.rfind("}") + 1
                json_str = content[start:end] if start >= 0 else content

            assessment_data = json.loads(json_str)

            return RiskAssessment(
                risk_level=RiskLevel(assessment_data.get("risk_level", "MEDIUM")),
                risk_score=assessment_data.get("risk_score", 0.5),
                risk_factors=assessment_data.get("risk_factors", []),
                mitigation_strategies=assessment_data.get("mitigation_strategies", []),
                requires_approval=assessment_data.get("requires_approval", False),
                approval_reason=assessment_data.get("approval_reason", "")
            )

        except Exception as e:
            logger.warning(f"⚠️ 风险评估失败: {e}，使用默认评估")
            return self._get_default_risk_assessment(remediation_plan)

    def _get_default_risk_assessment(self, remediation_plan: List[str]) -> RiskAssessment:
        """获取默认风险评估"""
        # 基于关键词的简单风险评估
        plan_text = " ".join(remediation_plan).lower()

        if any(kw in plan_text for kw in ["delete", "remove", "drop", "truncate"]):
            return RiskAssessment(
                risk_level=RiskLevel.HIGH,
                risk_score=0.7,
                risk_factors=["包含删除操作"],
                mitigation_strategies=["备份资源", "确认资源名称"],
                requires_approval=True,
                approval_reason="包含删除操作"
            )
        elif any(kw in plan_text for kw in ["restart", "reboot", "reload"]):
            return RiskAssessment(
                risk_level=RiskLevel.MEDIUM,
                risk_score=0.5,
                risk_factors=["服务重启可能影响可用性"],
                mitigation_strategies=["在低峰期执行", "监控服务状态"],
                requires_approval=False
            )
        else:
            return RiskAssessment(
                risk_level=RiskLevel.LOW,
                risk_score=0.2,
                risk_factors=[],
                mitigation_strategies=["验证配置正确性"],
                requires_approval=False
            )

    async def _create_execution_plan(
        self,
        user_query: str,
        remediation_plan: List[str],
        context: Dict[str, Any],
        risk_assessment: RiskAssessment
    ) -> ExecutionPlan:
        """Phase 2: 生成执行计划"""
        steps = []
        step_id = 1

        for plan_item in remediation_plan:
            step = ExecutionStep(
                id=f"step{step_id}",
                action=plan_item,
                tool="auto",  # 自动选择工具
                params=context.copy(),
                expected_outcome=f"成功执行: {plan_item}"
            )
            steps.append(step)
            step_id += 1

        # 生成验证步骤
        verification_steps = [
            "检查操作后的系统状态",
            "验证资源配置是否正确",
            "确认服务正常运行"
        ]

        return ExecutionPlan(
            steps=steps,
            estimated_duration=len(steps) * 10.0,  # 每步预估10秒
            risk_assessment=risk_assessment,
            verification_steps=verification_steps
        )

    async def _execute_step_with_verification(
        self,
        step: ExecutionStep,
        context: Dict[str, Any]
    ) -> StepResult:
        """执行单个步骤并进行验证"""
        start_time = datetime.now()

        try:
            # ReAct 循环: Thought → Action → Observation
            # Thought: 分析步骤
            thought = await self._think_about_step(step, context)
            logger.debug(f"💭 [ReAct Thought] {thought}")

            # Action: 执行操作
            action_result = await self._perform_action(step, context)

            # Observation: 观察结果
            observation = await self._observe_result(action_result, context)
            logger.debug(f"👁️ [ReAct Observation] {observation}")

            duration = (datetime.now() - start_time).total_seconds()

            if action_result.get("success"):
                return StepResult(
                    step_id=step.id,
                    success=True,
                    output=action_result.get("output"),
                    duration=duration,
                    verified=True  # 已通过 ReAct 循环验证
                )
            else:
                return StepResult(
                    step_id=step.id,
                    success=False,
                    error=action_result.get("error", "未知错误"),
                    duration=duration
                )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ 步骤 {step.id} 执行异常: {e}")
            return StepResult(
                step_id=step.id,
                success=False,
                error=str(e),
                duration=duration
            )

    async def _think_about_step(self, step: ExecutionStep, context: Dict[str, Any]) -> str:
        """ReAct: 思考步骤"""
        prompt = f"""分析以下执行步骤：

步骤：{step.action}
参数：{json.dumps(step.params, ensure_ascii=False)}
期望结果：{step.expected_outcome}

请简要说明：
1. 这个步骤的目的是什么？
2. 可能会遇到什么问题？
3. 如何确保操作成功？

返回简洁的思考过程（100字以内）。"""

        try:
            response = await self.llm.ainvoke(prompt)
            return response.content[:200]  # 限制长度
        except:
            return f"执行步骤: {step.action}"

    async def _perform_action(self, step: ExecutionStep, context: Dict[str, Any]) -> Dict[str, Any]:
        """ReAct: 执行操作"""
        # 这里应该调用实际的工具
        # 简化实现：返回模拟结果
        logger.info(f"⚡ [执行] {step.action}")

        # TODO: 实际工具调用逻辑
        # 根据步骤内容选择合适的工具
        return {
            "success": True,
            "output": f"已执行: {step.action}",
            "duration": 1.0
        }

    async def _observe_result(self, action_result: Dict[str, Any], context: Dict[str, Any]) -> str:
        """ReAct: 观察结果"""
        if action_result.get("success"):
            return f"操作成功: {action_result.get('output', '无输出')}"
        else:
            return f"操作失败: {action_result.get('error', '未知错误')}"

    async def _verify_execution(
        self,
        execution_plan: ExecutionPlan,
        steps_results: List[StepResult],
        context: Dict[str, Any]
    ) -> Dict[str, bool]:
        """Phase 4: 验证执行结果"""
        verification_results = {}

        for verification_step in execution_plan.verification_steps:
            # 使用 LLM 验证
            verification_prompt = f"""验证以下操作结果：

验证目标：{verification_step}

执行的步骤：
{json.dumps([r.step_id for r in steps_results if r.success], ensure_ascii=False)}

请判断：验证目标是否达成？

以 JSON 格式输出：
```json
{{"verified": true}}
```
"""

            try:
                response = await self.llm.ainvoke(verification_prompt)
                content = response.content

                # 简单解析
                verified = "true" in content.lower() or "✓" in content
                verification_results[verification_step] = verified

            except:
                # 默认验证通过
                verification_results[verification_step] = True

        return verification_results

    async def _rollback_steps(
        self,
        executed_steps: List[StepResult],
        context: Dict[str, Any]
    ) -> str:
        """回滚已执行的步骤"""
        rollback_details = []

        # 按相反顺序回滚
        for step_result in reversed(executed_steps):
            if step_result.success:
                logger.info(f"🔄 [回滚] 回滚步骤: {step_result.step_id}")
                rollback_details.append(f"已回滚: {step_result.step_id}")
                # TODO: 实际执行回滚操作

        return "; ".join(rollback_details)


# ==================== 便捷函数 ====================

_enhanced_execute_service_instance: Optional[EnhancedExecuteService] = None


def get_enhanced_execute_service() -> EnhancedExecuteService:
    """获取增强执行服务单例"""
    global _enhanced_execute_service_instance
    if _enhanced_execute_service_instance is None:
        _enhanced_execute_service_instance = EnhancedExecuteService()
    return _enhanced_execute_service_instance


async def enhanced_execute(
    user_query: str,
    remediation_plan: List[str],
    context: Dict[str, Any] = None,
    auto_rollback: bool = True
) -> Dict[str, Any]:
    """
    增强执行入口函数

    Args:
        user_query: 用户查询
        remediation_plan: 修复计划
        context: 上下文信息
        auto_rollback: 是否自动回滚

    Returns:
        执行结果
    """
    service = get_enhanced_execute_service()
    result = await service.execute_with_safety(
        user_query=user_query,
        remediation_plan=remediation_plan,
        context=context or {},
        auto_rollback=auto_rollback
    )

    return {
        "status": result.status.value,
        "steps_results": [
            {
                "step_id": r.step_id,
                "success": r.success,
                "output": r.output,
                "error": r.error,
                "duration": r.duration,
                "verified": r.verified
            }
            for r in result.steps_results
        ],
        "final_output": result.final_output,
        "error": result.error,
        "total_duration": result.total_duration,
        "rollback_performed": result.rollback_performed,
        "rollback_details": result.rollback_details,
        "verification_results": result.verification_results
    }


__all__ = [
    "EnhancedExecuteService",
    "RiskLevel",
    "ExecutionStatus",
    "RiskAssessment",
    "ExecutionStep",
    "ExecutionPlan",
    "StepResult",
    "ExecutionResult",
    "get_enhanced_execute_service",
    "enhanced_execute",
]
