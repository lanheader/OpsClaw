# -*- coding: utf-8 -*-
"""
增强的数据采集服务 - 使用 ReWOO 模式

ReWOO (Reasoning WithOut Observation) 模式：
1. Planner: 一次性规划所有采集步骤
2. Worker: 并行执行所有采集步骤
3. Solver: 整合结果

优势：
- 执行效率高（并行采集）
- 减少 Token 消耗（无需中间观察）
- 步骤可并行（无依赖的数据源）
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime
from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm_factory import LLMFactory
from app.tools import get_tools_by_package
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ==================== 数据模型 ====================

@dataclass
class CollectionStep:
    """数据采集步骤"""
    id: str
    tool: str  # k8s, prometheus, loki
    action: str  # 具体操作
    params: Dict[str, Any]
    priority: int = 5  # 优先级 (1-10, 1最高)
    estimated_duration: float = 5.0  # 预估耗时（秒）
    dependencies: List[str] = field(default_factory=list)  # 依赖的步骤ID


@dataclass
class CollectionResult:
    """采集结果"""
    step_id: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    duration: float = 0.0
    source: str = ""  # sdk/cli


@dataclass
class CollectionPlan:
    """采集计划"""
    steps: List[CollectionStep] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    estimated_total_duration: float = 0.0


@dataclass
class IntegratedData:
    """整合后的数据"""
    raw_results: Dict[str, CollectionResult] = field(default_factory=dict)
    processed_data: Dict[str, Any] = field(default_factory=dict)
    summary: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ==================== ReWOO 采集服务 ====================

class EnhancedDataAgentService:
    """
    增强的数据采集服务 - 使用 ReWOO 模式

    工作流程：
    1. Planner: 分析用户需求，规划采集步骤
    2. Worker: 并行执行所有采集步骤
    3. Solver: 整合结果并生成摘要
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        self.llm = llm or LLMFactory.create_llm_for_subagent("data-agent")

        # 获取可用工具
        self.k8s_tools = get_tools_by_package("k8s")
        self.prometheus_tools = get_tools_by_package("prometheus")
        self.loki_tools = get_tools_by_package("loki")

        # 工具映射
        self._tool_map = {
            "k8s": self.k8s_tools,
            "prometheus": self.prometheus_tools,
            "loki": self.loki_tools,
        }

    async def collect_data_rewoo(
        self,
        user_query: str,
        context: Dict[str, Any] = None,
        collected_data: Dict[str, Any] = None
    ) -> IntegratedData:
        """
        使用 ReWOO 模式采集数据

        Args:
            user_query: 用户查询
            context: 上下文信息
            collected_data: 已采集的数据（部分采集场景）

        Returns:
            整合后的数据
        """
        context = context or {}
        logger.info(f"📊 [ReWOO] 开始数据采集: {user_query[:50]}")

        # Phase 1: Planner - 规划采集步骤
        plan = await self._plan_collection_steps(
            user_query=user_query,
            context=context,
            existing_data=collected_data
        )
        logger.info(f"📋 [Planner] 规划了 {len(plan.steps)} 个采集步骤")

        # Phase 2: Worker - 并行执行采集
        results = await self._execute_collection_parallel(plan)
        logger.info(f"✅ [Worker] 完成 {len(results)} 个采集步骤")

        # Phase 3: Solver - 整合结果
        integrated_data = await self._integrate_results(
            plan=plan,
            results=results,
            user_query=user_query
        )
        logger.info(f"🔍 [Solver] 数据整合完成")

        return integrated_data

    async def _plan_collection_steps(
        self,
        user_query: str,
        context: Dict[str, Any],
        existing_data: Dict[str, Any] = None,
        memory_context: str = ""
    ) -> CollectionPlan:
        """
        Phase 1 (Planner): 规划采集步骤（带记忆增强）

        使用 CoT 推理分析用户需求，生成采集计划
        """
        existing_info = ""
        if existing_data:
            existing_info = f"\n已采集的数据:\n{json.dumps(existing_data, ensure_ascii=False, indent=2)}"

        context_info = ""
        if context:
            context_info = f"\n上下文信息:\n{json.dumps(context, ensure_ascii=False, indent=2)}"

        prompt = f"""作为运维数据采集专家，请分析以下用户需求，规划需要采集的数据：

用户需求：{user_query}{context_info}{existing_info}{memory_context}

可用数据源：
- K8s: Pod、Node、Deployment、Service、ConfigMap、Secret 等
- Prometheus: 监控指标（CPU、内存、磁盘、网络等）
- Loki: 日志查询

请使用 Chain of Thought 推理：

**步骤1：需求分析**
- 用户想了解什么？
- 需要哪些关键指标？
- 涉及哪些系统/组件？

**步骤2：数据源选择**
- 哪些数据源能提供所需信息？
- 每个数据源需要什么操作？

**步骤3：采集规划**
请以 JSON 格式输出采集计划：
```json
{{
  "steps": [
    {{
      "id": "step1",
      "tool": "k8s",
      "action": "get_pods",
      "params": {{"namespace": "default"}},
      "priority": 1,
      "estimated_duration": 2.0,
      "reasoning": "获取 Pod 列表查看应用状态"
    }},
    {{
      "id": "step2",
      "tool": "prometheus",
      "action": "query_range",
      "params": {{"query": "up", "duration": "5m"}},
      "priority": 2,
      "estimated_duration": 3.0,
      "reasoning": "查询最近5分钟的可用性指标"
    }}
  ]
}}
```

注意：
- 只规划必要的采集步骤
- 优先级 1-10（1最高）
- 估算每个步骤的耗时
- 独立的数据源可以并行采集
"""

        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content

            # 解析 JSON
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
            elif "```" in content:
                json_start = content.find("```") + 3
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
            else:
                start = content.find("{")
                end = content.rfind("}") + 1
                json_str = content[start:end] if start >= 0 else content

            parsed = json.loads(json_str)

            steps = []
            total_duration = 0.0

            for i, step_data in enumerate(parsed.get("steps", [])):
                step = CollectionStep(
                    id=step_data.get("id", f"step{i+1}"),
                    tool=step_data.get("tool", ""),
                    action=step_data.get("action", ""),
                    params=step_data.get("params", {}),
                    priority=step_data.get("priority", 5),
                    estimated_duration=step_data.get("estimated_duration", 5.0),
                    dependencies=step_data.get("dependencies", [])
                )
                steps.append(step)
                total_duration += step.estimated_duration

            return CollectionPlan(
                steps=steps,
                metadata={
                    "user_query": user_query,
                    "planned_at": datetime.now().isoformat()
                },
                estimated_total_duration=total_duration
            )

        except Exception as e:
            logger.error(f"❌ [Planner] 规划失败: {e}")
            # 返回默认计划
            return self._get_default_plan(user_query, context)

    def _get_default_plan(
        self,
        user_query: str,
        context: Dict[str, Any]
    ) -> CollectionPlan:
        """生成默认采集计划（规划失败时的后备方案）"""
        query_lower = user_query.lower()

        steps = []
        step_id = 1

        # 根据关键词决定采集哪些数据
        if any(kw in query_lower for kw in ["pod", "容器", "deployment", "应用"]):
            steps.append(CollectionStep(
                id=f"step{step_id}",
                tool="k8s",
                action="get_pods",
                params={"namespace": context.get("namespace", "default")},
                priority=1,
                estimated_duration=2.0
            ))
            step_id += 1

        if any(kw in query_lower for kw in ["指标", "监控", "cpu", "内存", "prometheus", "prom"]):
            steps.append(CollectionStep(
                id=f"step{step_id}",
                tool="prometheus",
                action="query_range",
                params={"query": "up", "duration": "5m"},
                priority=2,
                estimated_duration=3.0
            ))
            step_id += 1

        if any(kw in query_lower for kw in ["日志", "log", "error", "错误"]):
            steps.append(CollectionStep(
                id=f"step{step_id}",
                tool="loki",
                action="query_logs",
                params={"query": "", "limit": 100},
                priority=3,
                estimated_duration=5.0
            ))
            step_id += 1

        # 如果没有明确指示，采集基础数据
        if not steps:
            steps.append(CollectionStep(
                id="step1",
                tool="k8s",
                action="get_pods",
                params={"namespace": "default"},
                priority=1,
                estimated_duration=2.0
            ))

        return CollectionPlan(
            steps=steps,
            metadata={"fallback": True},
            estimated_total_duration=sum(s.estimated_duration for s in steps)
        )

    async def _execute_collection_parallel(
        self,
        plan: CollectionPlan
    ) -> List[CollectionResult]:
        """
        Phase 2 (Worker): 并行执行采集步骤

        优化策略：
        - 按优先级分组执行
        - 高优先级先执行
        - 无依赖的步骤可以并行
        """
        results = []

        # 按优先级分组
        priority_groups = {}
        for step in plan.steps:
            priority = step.priority
            if priority not in priority_groups:
                priority_groups[priority] = []
            priority_groups[priority].append(step)

        # 按优先级顺序执行
        for priority in sorted(priority_groups.keys()):
            steps_in_priority = priority_groups[priority]

            # 找出无依赖的步骤（可以并行）
            parallel_steps = []
            for step in steps_in_priority:
                # 检查依赖是否满足
                deps_satisfied = all(
                    any(r.step_id == dep for r in results)
                    for dep in step.dependencies
                )
                if deps_satisfied or not step.dependencies:
                    parallel_steps.append(step)

            if parallel_steps:
                logger.info(f"🔄 [Worker] 并行执行 {len(parallel_steps)} 个步骤 (优先级 {priority})")
                # 并行执行
                step_results = await asyncio.gather(*[
                    self._execute_single_step(step)
                    for step in parallel_steps
                ])
                results.extend(step_results)

        return results

    async def _execute_single_step(
        self,
        step: CollectionStep
    ) -> CollectionResult:
        """执行单个采集步骤"""
        start_time = datetime.now()

        try:
            logger.debug(f"📍 执行步骤 {step.id}: {step.tool}.{step.action}")

            # 获取对应工具
            tools = self._tool_map.get(step.tool, [])

            # 查找匹配的工具函数
            tool_func = None
            for t in tools:
                if hasattr(t, 'name') and step.action in str(t.name):
                    tool_func = t
                    break
                elif step.action in str(t.__name__):
                    tool_func = t
                    break

            if tool_func is None:
                # 尝试通过工具名称直接查找
                for t in tools:
                    if step.action in str(t):
                        tool_func = t
                        break

            if tool_func:
                # 执行工具
                if asyncio.iscoroutinefunction(tool_func):
                    result = await tool_func(**step.params)
                else:
                    result = tool_func(**step.params)

                duration = (datetime.now() - start_time).total_seconds()

                return CollectionResult(
                    step_id=step.id,
                    success=True,
                    data=result,
                    duration=duration,
                    source=getattr(tool_func, '__name__', str(tool_func))
                )
            else:
                # 工具未找到
                duration = (datetime.now() - start_time).total_seconds()
                return CollectionResult(
                    step_id=step.id,
                    success=False,
                    error=f"工具未找到: {step.tool}.{step.action}",
                    duration=duration
                )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ 步骤 {step.id} 执行失败: {e}")
            return CollectionResult(
                step_id=step.id,
                success=False,
                error=str(e),
                duration=duration
            )

    async def _integrate_results(
        self,
        plan: CollectionPlan,
        results: List[CollectionResult],
        user_query: str
    ) -> IntegratedData:
        """
        Phase 3 (Solver): 整合结果

        1. 汇总原始结果
        2. 提取关键信息
        3. 生成数据摘要
        """
        # 构建原始结果映射
        raw_results = {r.step_id: r for r in results}

        # 处理数据
        processed_data = {}
        summary = {
            "total_steps": len(plan.steps),
            "successful_steps": sum(1 for r in results if r.success),
            "failed_steps": sum(1 for r in results if not r.success),
            "total_duration": sum(r.duration for r in results),
            "data_sources": set(),
            "data_types": [],
        }

        for result in results:
            if result.success:
                # 提取数据类型和来源
                summary["data_sources"].add(result.source)

                # 处理不同类型的数据
                if isinstance(result.data, dict):
                    processed_data.update(result.data)
                elif isinstance(result.data, list):
                    processed_data[f"{result.step_id}_data"] = result.data
                else:
                    processed_data[f"{result.step_id}_data"] = result.data

        # 转换 set 为 list
        summary["data_sources"] = list(summary["data_sources"])

        # 使用 LLM 生成摘要
        data_summary = await self._generate_data_summary(
            user_query=user_query,
            processed_data=processed_data,
            raw_results=raw_results
        )

        summary.update(data_summary)

        return IntegratedData(
            raw_results=raw_results,
            processed_data=processed_data,
            summary=summary,
            metadata={
                "plan_metadata": plan.metadata,
                "integrated_at": datetime.now().isoformat()
            }
        )

    async def _generate_data_summary(
        self,
        user_query: str,
        processed_data: Dict[str, Any],
        raw_results: Dict[str, CollectionResult]
    ) -> Dict[str, Any]:
        """
        使用 LLM 生成数据摘要

        1. 关键发现
        2. 异常指标
        3. 数据质量评估
        """
        # 格式化数据为字符串（简化版）
        data_str = json.dumps(processed_data, ensure_ascii=False, indent=2)[:2000]

        prompt = f"""请分析以下采集的数据, 生成简洁摘要:

        用户需求: {user_query}

        采集的数据:
        {data_str}

        请提供:
        1. key_findings: 关键发现(数组, 最多5条)
        2. issues: 异常情况(数组, 最多3条)
        3. data_quality: 数据质量评估(good/partial/poor)

        以 JSON 格式输出:
        ```json
        {{
          "key_findings": ["发现1", "发现2"],
          "issues": ["异常1", "异常2"],
          "data_quality": "good"
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

            summary = json.loads(json_str)
            return summary

        except Exception as e:
            logger.warning(f"⚠️ 数据摘要生成失败: {e}")
            # 返回默认摘要
            return {
                "key_findings": [f"采集了 {len(processed_data)} 类数据"],
                "issues": [],
                "data_quality": "good"
            }


# ==================== 便捷函数 ====================

_data_agent_service_instance: Optional[EnhancedDataAgentService] = None


def get_enhanced_data_agent_service() -> EnhancedDataAgentService:
    """获取增强数据采集服务单例"""
    global _data_agent_service_instance
    if _data_agent_service_instance is None:
        _data_agent_service_instance = EnhancedDataAgentService()
    return _data_agent_service_instance


async def enhanced_collect_data(
    user_query: str,
    context: Dict[str, Any] = None,
    collected_data: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    增强数据采集入口函数（兼容旧接口）

    使用 ReWOO 模式并行采集数据

    Args:
        user_query: 用户查询
        context: 上下文信息
        collected_data: 已采集的数据

    Returns:
        采集和整合后的数据
    """
    service = get_enhanced_data_agent_service()
    result = await service.collect_data_rewoo(
        user_query=user_query,
        context=context or {},
        collected_data=collected_data
    )

    return {
        "raw_results": {k: {
            "success": v.success,
            "data": v.data,
            "error": v.error,
            "duration": v.duration
        } for k, v in result.raw_results.items()},
        "processed_data": result.processed_data,
        "summary": result.summary,
        "metadata": result.metadata
    }


__all__ = [
    "EnhancedDataAgentService",
    "CollectionStep",
    "CollectionResult",
    "CollectionPlan",
    "IntegratedData",
    "get_enhanced_data_agent_service",
    "enhanced_collect_data",
]
数 ====================

_data_agent_service_instance: Optional[EnhancedDataAgentService] = None


def get_enhanced_data_agent_service() -> EnhancedDataAgentService:
    """获取增强数据采集服务单例"""
    global _data_agent_service_instance
    if _data_agent_service_instance is None:
        _data_agent_service_instance = EnhancedDataAgentService()
    return _data_agent_service_instance


async def enhanced_collect_data(
    user_query: str,
    context: Dict[str, Any] = None,
    collected_data: Dict[str, Any] = None

    
    def _should_use_memory(self, query: str) -> bool:
        """
        判断是否需要使用记忆（参考 OpenClaw）
        
        规则：
        - 具体资源查询（版本、配置、状态、日志）→ 不使用记忆
        - 故障诊断（错误、异常、失败、告警）→ 使用记忆
        - 其他查询 → 使用记忆
        
        Args:
            query: 用户查询
        
        Returns:
            是否需要使用记忆
        """
        query_lower = query.lower()
        
        # 具体资源查询 → 不使用记忆
        specific_keywords = ["版本", "version", "配置", "config", "状态", "status", "日志", "log", "yaml"]
        if any(kw in query_lower for kw in specific_keywords):
            return False
        
        # 故障诊断 → 使用记忆
        diagnosis_keywords = ["错误", "error", "异常", "exception", "失败", "fail", "告警", "alert", "故障", "诊断", "排查"]
        if any(kw in query_lower for kw in diagnosis_keywords):
            return True
        
        # 默认使用记忆
        return False

) -> Dict[str, Any]:
    """
    增强数据采集入口函数（兼容旧接口）

    使用 ReWOO 模式并行采集数据

    Args:
        user_query: 用户查询
        context: 上下文信息
        collected_data: 已采集的数据

    Returns:
        采集和整合后的数据
    """
    service = get_enhanced_data_agent_service()
    result = await service.collect_data_rewoo(
        user_query=user_query,
        context=context or {},
        collected_data=collected_data
    )

    return {
        "raw_results": {k: {
            "success": v.success,
            "data": v.data,
            "error": v.error,
            "duration": v.duration
        } for k, v in result.raw_results.items()},
        "processed_data": result.processed_data,
        "summary": result.summary,
        "metadata": result.metadata
    }


__all__ = [
    "EnhancedDataAgentService",
    "CollectionStep",
    "CollectionResult",
    "CollectionPlan",
    "IntegratedData",
    "get_enhanced_data_agent_service",
    "enhanced_collect_data",
]
