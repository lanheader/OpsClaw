"""
增强的主智能体服务 - 使用 CoT + Plan-and-Solve

设计模式组合：
1. CoT (Chain of Thought): 显式推理链
2. Plan-and-Solve: 详细任务规划
3. Self-Reflection: 规划评估和调整

核心流程：
1. 理解用户需求（Comprehension）
2. CoT 推理分析（Reasoning）
3. 生成执行计划（Planning）
4. 评估计划质量（Evaluation）
5. 委派执行（Delegation）
6. 监控执行进度（Monitoring）
7. 整合结果（Synthesis）
"""

import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from langchain_core.language_models import BaseChatModel

from app.core.llm_factory import LLMFactory
from app.deepagents.subagents import get_all_subagents
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ==================== 辅助函数 ====================

def _extract_json_from_response(content: str) -> Optional[Dict]:
    """从 LLM 响应中提取 JSON"""
    try:
        # 尝试提取 ```json ... ``` 块
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            return json.loads(content[start:end].strip())

        # 尝试提取 ``` ... ``` 块
        if "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            return json.loads(content[start:end].strip())

        # 尝试提取第一个 JSON 对象
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])

    except json.JSONDecodeError:
        pass

    return None


# ==================== 枚举类型 ====================

class TaskComplexity(Enum):
    """任务复杂度"""
    SIMPLE = "simple"  # 单一操作，无需规划
    MODERATE = "moderate"  # 需要少量步骤
    COMPLEX = "complex"  # 多步骤，需要协调
    VERY_COMPLEX = "very_complex"  # 涉及多个子智能体


class TaskType(Enum):
    """任务类型"""
    QUERY = "query"  # 查询类
    DIAGNOSIS = "diagnosis"  # 诊断类
    REMEDIATION = "remediation"  # 修复类
    REPORT = "report"  # 报告类
    UNKNOWN = "unknown"


class PlanningStatus(Enum):
    """规划状态"""
    DRAFT = "draft"
    EVALUATING = "evaluating"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISED = "revised"


# ==================== 数据模型 ====================

@dataclass
class ReasoningStep:
    """推理步骤"""
    step_number: int
    thought: str  # 思考内容
    rationale: str  # 理由
    conclusion: str  # 结论
    confidence: float  # 置信度 (0.0 - 1.0)


@dataclass
class TaskPlan:
    """任务计划"""
    plan_id: str
    user_query: str
    task_type: TaskType
    complexity: TaskComplexity
    reasoning_chain: List[ReasoningStep]  # CoT 推理链
    subtasks: List[Dict[str, Any]]  # 子任务列表
    estimated_duration: float  # 预估耗时（秒）
    required_subagents: List[str]  # 需要的子智能体
    status: PlanningStatus = PlanningStatus.DRAFT
    evaluation_score: float = 0.0  # 计划评估分数
    revision_history: List[str] = field(default_factory=list)


@dataclass
class SubTaskExecution:
    """子任务执行状态"""
    subtask_id: str
    assigned_to: str  # 委派给哪个子智能体
    status: str  # pending, in_progress, completed, failed
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class ExecutionSummary:
    """执行摘要"""
    plan_id: str
    user_query: str
    total_duration: float
    subtasks_completed: int
    subtasks_failed: int
    final_result: Any = None
    reasoning_summary: str = ""  # 推理摘要
    lessons_learned: List[str] = field(default_factory=list)


# ==================== 增强主智能体服务 ====================

class EnhancedMainAgentService:
    """
    增强的主智能体服务 - 使用 CoT + Plan-and-Solve

    工作流程：
    1. Comprehension: 理解用户需求
    2. CoT Reasoning: 显式推理分析
    3. Planning: 生成执行计划
    4. Evaluation: 评估计划质量
    5. Delegation: 委派给子智能体
    6. Monitoring: 监控执行进度
    7. Synthesis: 整合结果
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        self.llm = llm or LLMFactory.create_llm()
        self.subagents = get_all_subagents()
        self.planning_history: List[TaskPlan] = []

    async def process_user_request(
        self,
        user_query: str,
        context: Dict[str, Any] = None,
        enable_cot: bool = True,
        enable_plan_evaluation: bool = True
    ) -> ExecutionSummary:
        """
        处理用户请求（使用 CoT + Plan-and-Solve）

        Args:
            user_query: 用户查询
            context: 上下文信息
            enable_cot: 是否启用 CoT 推理
            enable_plan_evaluation: 是否启用计划评估

        Returns:
            执行摘要
        """
        context = context or {}
        start_time = datetime.now()

        logger.info(f"🧠 [EnhancedMainAgent] 开始处理: {user_query[:50]}...")

        # Phase 1: Comprehension - 理解用户需求
        task_type, complexity = await self._comprehend_request(user_query, context)
        logger.info(f"📖 [理解] 任务类型: {task_type.value}, 复杂度: {complexity.value}")

        # Phase 2: CoT Reasoning - 显式推理分析
        reasoning_chain = []
        if enable_cot:
            reasoning_chain = await self._generate_reasoning_chain(
                user_query=user_query,
                task_type=task_type,
                complexity=complexity,
                context=context
            )
            logger.info(f"💭 [CoT] 生成了 {len(reasoning_chain)} 个推理步骤")

        # Phase 3: Planning - 生成执行计划
        task_plan = await self._create_task_plan(
            user_query=user_query,
            task_type=task_type,
            complexity=complexity,
            reasoning_chain=reasoning_chain,
            context=context
        )
        logger.info(f"📋 [规划] 生成了 {len(task_plan.subtasks)} 个子任务")

        # Phase 4: Evaluation - 评估计划质量
        if enable_plan_evaluation:
            evaluation_result = await self._evaluate_plan(task_plan, context)
            task_plan.evaluation_score = evaluation_result["score"]
            task_plan.status = PlanningStatus.APPROVED if evaluation_result["approved"] else PlanningStatus.REJECTED
            logger.info(f"✓ [评估] 计划分数: {evaluation_result['score']:.2f}, 状态: {task_plan.status.value}")

        # 保存规划历史
        self.planning_history.append(task_plan)

        # Phase 5: Delegation - 委派给子智能体
        subtask_executions = await self._delegate_subtasks(task_plan, context)

        # Phase 6: Monitoring - 监控执行进度
        completed, failed = await self._monitor_execution(subtask_executions, context)

        # Phase 7: Synthesis - 整合结果
        total_duration = (datetime.now() - start_time).total_seconds()
        execution_summary = await self._synthesize_results(
            task_plan=task_plan,
            subtask_executions=subtask_executions,
            total_duration=total_duration
        )

        logger.info(f"✅ [完成] 处理完成，耗时 {total_duration:.2f}秒")

        return execution_summary

    async def _comprehend_request(
        self,
        user_query: str,
        context: Dict[str, Any]
    ) -> Tuple[TaskType, TaskComplexity]:
        """Phase 1: 理解用户请求"""
        prompt = self._build_comprehension_prompt(user_query, context)

        try:
            response = await self.llm.ainvoke(prompt)
            result = _extract_json_from_response(response.content)

            if result:
                return (
                    TaskType(result.get("task_type", "QUERY")),
                    TaskComplexity(result.get("complexity", "SIMPLE"))
                )

            return self._default_comprehension(user_query)

        except Exception as e:
            logger.warning(f"⚠️ 请求理解失败: {e}，使用默认分析")
            return self._default_comprehension(user_query)

    def _build_comprehension_prompt(self, user_query: str, context: Dict[str, Any]) -> str:
        """构建理解提示词"""
        return f"""分析以下用户请求：

用户请求：{user_query}

上下文：
{json.dumps(context, ensure_ascii=False, indent=2)}

请判断：

1. 任务类型（QUERY/DIAGNOSIS/REMEDIATION/REPORT）：
   - QUERY: 查询信息、查看状态
   - DIAGNOSIS: 诊断问题、分析根因
   - REMEDIATION: 执行修复、解决问题
   - REPORT: 生成报告、汇总信息

2. 任务复杂度（SIMPLE/MODERATE/COMPLEX/VERY_COMPLEX）：
   - SIMPLE: 单一操作，无需规划
   - MODERATE: 需要少量步骤（2-3步）
   - COMPLEX: 多步骤，需要协调（4-7步）
   - VERY_COMPLEX: 涉及多个子智能体（8+步）

以 JSON 格式输出：
```json
{{
  "task_type": "QUERY",
  "complexity": "MODERATE",
  "reasoning": "用户想查询 Pod 状态，属于简单查询"
}}
```
"""

    def _default_comprehension(self, user_query: str) -> Tuple[TaskType, TaskComplexity]:
        """默认请求理解（基于关键词）"""
        query_lower = user_query.lower()

        # 判断任务类型
        if any(kw in query_lower for kw in ["查询", "查看", "什么", "多少", "list", "get", "show"]):
            task_type = TaskType.QUERY
        elif any(kw in query_lower for kw in ["诊断", "分析", "为什么", "原因", "diagnose", "analyze"]):
            task_type = TaskType.DIAGNOSIS
        elif any(kw in query_lower for kw in ["修复", "重启", "删除", "执行", "fix", "restart", "delete"]):
            task_type = TaskType.REMEDIATION
        elif any(kw in query_lower for kw in ["报告", "汇总", "统计", "report", "summary"]):
            task_type = TaskType.REPORT
        else:
            task_type = TaskType.QUERY

        # 判断复杂度
        if "，" in user_query or "；" in user_query or " then " in user_query:
            complexity = TaskComplexity.COMPLEX
        elif any(kw in query_lower for kw in ["然后", "接着", "之后", "then"]):
            complexity = TaskComplexity.MODERATE
        else:
            complexity = TaskComplexity.SIMPLE

        return task_type, complexity

    async def _generate_reasoning_chain(
        self,
        user_query: str,
        task_type: TaskType,
        complexity: TaskComplexity,
        context: Dict[str, Any]
    ) -> List[ReasoningStep]:
        """Phase 2: 生成 CoT 推理链"""
        prompt = self._build_reasoning_prompt(user_query, task_type, complexity, context)

        try:
            response = await self.llm.ainvoke(prompt)
            result = _extract_json_from_response(response.content)

            if result and "reasoning_steps" in result:
                return self._parse_reasoning_steps(result["reasoning_steps"])

            return self._get_default_reasoning_chain(user_query, task_type)

        except Exception as e:
            logger.warning(f"⚠️ CoT 推理失败: {e}，使用默认推理")
            return self._get_default_reasoning_chain(user_query, task_type)

    def _build_reasoning_prompt(
        self,
        user_query: str,
        task_type: TaskType,
        complexity: TaskComplexity,
        context: Dict[str, Any]
    ) -> str:
        """构建推理提示词"""
        return f"""使用链式思考（Chain of Thought）分析以下请求：

用户请求：{user_query}
任务类型：{task_type.value}
任务复杂度：{complexity.value}

上下文：
{json.dumps(context, ensure_ascii=False, indent=2)}

请逐步推理：

**步骤1：需求分析**
- 用户真正想要什么？
- 有哪些隐含需求？

**步骤2：信息评估**
- 已知哪些信息？
- 需要收集哪些信息？

**步骤3：方案制定**
- 有哪些可能的方案？
- 每种方案的优缺点？

**步骤4：执行规划**
- 最佳方案是什么？
- 具体执行步骤是什么？

请以 JSON 格式输出推理链：
```json
{{
  "reasoning_steps": [
    {{
      "step_number": 1,
      "thought": "分析用户需求",
      "rationale": "用户想知道 Pod 状态",
      "conclusion": "需要查询 K8s API",
      "confidence": 0.9
    }},
    {{
      "step_number": 2,
      "thought": "确定数据源",
      "rationale": "Pod 信息在 K8s 集群中",
      "conclusion": "使用 k8s_tools.get_pods",
      "confidence": 0.95
    }}
  ]
}}
```
"""

    def _parse_reasoning_steps(self, steps_data: List[Dict]) -> List[ReasoningStep]:
        """解析推理步骤"""
        return [
            ReasoningStep(
                step_number=step.get("step_number", i + 1),
                thought=step.get("thought", ""),
                rationale=step.get("rationale", ""),
                conclusion=step.get("conclusion", ""),
                confidence=step.get("confidence", 0.5)
            )
            for i, step in enumerate(steps_data)
        ]

    def _get_default_reasoning_chain(self, user_query: str, task_type: TaskType) -> List[ReasoningStep]:
        """获取默认推理链"""
        return [
            ReasoningStep(
                step_number=1,
                thought="理解用户意图",
                rationale=f"用户请求: {user_query}",
                conclusion="需要处理此请求",
                confidence=0.8
            ),
            ReasoningStep(
                step_number=2,
                thought="确定执行方案",
                rationale=f"任务类型: {task_type.value}",
                conclusion="委派给相应的子智能体",
                confidence=0.9
            )
        ]

    async def _create_task_plan(
        self,
        user_query: str,
        task_type: TaskType,
        complexity: TaskComplexity,
        reasoning_chain: List[ReasoningStep],
        context: Dict[str, Any]
    ) -> TaskPlan:
        """Phase 3: 生成执行计划"""
        # 根据任务类型和复杂度生成子任务
        subtasks = []
        required_subagents = []

        if task_type == TaskType.QUERY:
            subtasks.append({
                "subtask_id": "subtask1",
                "description": "采集数据",
                "assigned_to": "data-agent",
                "params": {"query": user_query}
            })
            required_subagents.append("data-agent")

        elif task_type == TaskType.DIAGNOSIS:
            subtasks.append({
                "subtask_id": "subtask1",
                "description": "采集诊断数据",
                "assigned_to": "data-agent",
                "params": {"query": user_query}
            })
            subtasks.append({
                "subtask_id": "subtask2",
                "description": "分析诊断结果",
                "assigned_to": "analyze-agent",
                "params": {"data_from": "subtask1"}
            })
            required_subagents.extend(["data-agent", "analyze-agent"])

        elif task_type == TaskType.REMEDIATION:
            subtasks.append({
                "subtask_id": "subtask1",
                "description": "采集当前状态",
                "assigned_to": "data-agent",
                "params": {"query": user_query}
            })
            subtasks.append({
                "subtask_id": "subtask2",
                "description": "分析问题根因",
                "assigned_to": "analyze-agent",
                "params": {"data_from": "subtask1"}
            })
            subtasks.append({
                "subtask_id": "subtask3",
                "description": "执行修复操作",
                "assigned_to": "execute-agent",
                "params": {"plan_from": "subtask2"}
            })
            required_subagents.extend(["data-agent", "analyze-agent", "execute-agent"])

        # 计算预估耗时
        estimated_duration = len(subtasks) * 10.0  # 每个任务预估10秒

        return TaskPlan(
            plan_id=f"plan_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            user_query=user_query,
            task_type=task_type,
            complexity=complexity,
            reasoning_chain=reasoning_chain,
            subtasks=subtasks,
            estimated_duration=estimated_duration,
            required_subagents=required_subagents,
            status=PlanningStatus.DRAFT
        )

    async def _evaluate_plan(
        self,
        task_plan: TaskPlan,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Phase 4: 评估计划质量"""
        prompt = self._build_evaluation_prompt(task_plan)

        try:
            response = await self.llm.ainvoke(prompt)
            result = _extract_json_from_response(response.content)

            if result:
                return {
                    "score": result.get("score", 0.5),
                    "approved": result.get("approved", True),
                    "feedback": result.get("feedback", ""),
                    "suggestions": result.get("suggestions", [])
                }

            return self._get_default_evaluation()

        except Exception as e:
            logger.warning(f"⚠️ 计划评估失败: {e}，使用默认评估")
            return self._get_default_evaluation()

    def _build_evaluation_prompt(self, task_plan: TaskPlan) -> str:
        """构建评估提示词"""
        return f"""评估以下执行计划的质量：

计划信息：
- 任务类型: {task_plan.task_type.value}
- 复杂度: {task_plan.complexity.value}
- 子任务数: {len(task_plan.subtasks)}
- 预估耗时: {task_plan.estimated_duration:.1f}秒

推理链：
{json.dumps([{
    "step": r.step_number,
    "thought": r.thought,
    "conclusion": r.conclusion
} for r in task_plan.reasoning_chain], ensure_ascii=False, indent=2)}

子任务：
{json.dumps(task_plan.subtasks, ensure_ascii=False, indent=2)}

请评估：
1. 计划完整性 (0.0-1.0)：是否覆盖了所有必要步骤？
2. 逻辑合理性 (0.0-1.0)：步骤顺序是否合理？
3. 可行性 (0.0-1.0)：是否可以实际执行？
4. 效率性 (0.0-1.0)：是否是最优方案？

以 JSON 格式输出：
```json
{{
  "score": 0.85,
  "approved": true,
  "feedback": "计划完整且可行",
  "suggestions": ["建议添加验证步骤"]
}}
```
"""

    def _get_default_evaluation(self) -> Dict[str, Any]:
        """获取默认评估结果"""
        return {
            "score": 0.7,
            "approved": True,
            "feedback": "默认通过",
            "suggestions": []
        }

    async def _delegate_subtasks(
        self,
        task_plan: TaskPlan,
        context: Dict[str, Any]
    ) -> List[SubTaskExecution]:
        """Phase 5: 委派子任务"""
        executions = []

        for subtask in task_plan.subtasks:
            execution = SubTaskExecution(
                subtask_id=subtask["subtask_id"],
                assigned_to=subtask["assigned_to"],
                status="pending"
            )
            executions.append(execution)

            logger.info(f"📤 [委派] {subtask['subtask_id']} → {subtask['assigned_to']}")

        # TODO: 实际调用子智能体执行
        # 这里简化为模拟执行
        for execution in executions:
            execution.status = "completed"
            execution.start_time = datetime.now()
            execution.end_time = datetime.now()
            execution.result = {"status": "success", "output": "模拟执行结果"}

        return executions

    async def _monitor_execution(
        self,
        subtask_executions: List[SubTaskExecution],
        context: Dict[str, Any]
    ) -> Tuple[int, int]:
        """Phase 6: 监控执行进度"""
        completed = sum(1 for e in subtask_executions if e.status == "completed")
        failed = sum(1 for e in subtask_executions if e.status == "failed")

        logger.info(f"📊 [监控] 完成: {completed}, 失败: {failed}")

        return completed, failed

    async def _synthesize_results(
        self,
        task_plan: TaskPlan,
        subtask_executions: List[SubTaskExecution],
        total_duration: float
    ) -> ExecutionSummary:
        """Phase 7: 整合结果"""
        # 生成推理摘要
        reasoning_summary = " | ".join([
            f"步骤{r.step_number}: {r.conclusion}"
            for r in task_plan.reasoning_chain
        ])

        # 提取经验教训
        lessons_learned = []
        if task_plan.evaluation_score < 0.7:
            lessons_learned.append("计划质量较低，建议改进规划流程")
        if any(e.status == "failed" for e in subtask_executions):
            lessons_learned.append("部分子任务失败，建议增加错误处理")

        return ExecutionSummary(
            plan_id=task_plan.plan_id,
            user_query=task_plan.user_query,
            total_duration=total_duration,
            subtasks_completed=len([e for e in subtask_executions if e.status == "completed"]),
            subtasks_failed=len([e for e in subtask_executions if e.status == "failed"]),
            reasoning_summary=reasoning_summary,
            lessons_learned=lessons_learned
        )


# ==================== 便捷函数 ====================

_enhanced_main_agent_service_instance: Optional[EnhancedMainAgentService] = None


def get_enhanced_main_agent_service() -> EnhancedMainAgentService:
    """获取增强主智能体服务单例"""
    global _enhanced_main_agent_service_instance
    if _enhanced_main_agent_service_instance is None:
        _enhanced_main_agent_service_instance = EnhancedMainAgentService()
    return _enhanced_main_agent_service_instance


async def enhanced_process_request(
    user_query: str,
    context: Dict[str, Any] = None,
    enable_cot: bool = True,
    enable_plan_evaluation: bool = True
) -> Dict[str, Any]:
    """
    增强请求处理入口函数

    Args:
        user_query: 用户查询
        context: 上下文信息
        enable_cot: 是否启用 CoT 推理
        enable_plan_evaluation: 是否启用计划评估

    Returns:
        处理结果
    """
    service = get_enhanced_main_agent_service()
    summary = await service.process_user_request(
        user_query=user_query,
        context=context or {},
        enable_cot=enable_cot,
        enable_plan_evaluation=enable_plan_evaluation
    )

    return {
        "plan_id": summary.plan_id,
        "user_query": summary.user_query,
        "total_duration": summary.total_duration,
        "subtasks_completed": summary.subtasks_completed,
        "subtasks_failed": summary.subtasks_failed,
        "final_result": summary.final_result,
        "reasoning_summary": summary.reasoning_summary,
        "lessons_learned": summary.lessons_learned
    }


__all__ = [
    "EnhancedMainAgentService",
    "TaskType",
    "TaskComplexity",
    "PlanningStatus",
    "ReasoningStep",
    "TaskPlan",
    "SubTaskExecution",
    "ExecutionSummary",
    "get_enhanced_main_agent_service",
    "enhanced_process_request",
]
