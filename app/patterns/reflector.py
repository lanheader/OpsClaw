"""
Self-Reflection 组件 - 执行前自检

功能：
- 操作风险评估
- 安全性审查
- 可逆性检查
- 改进建议生成
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pydantic import BaseModel

from app.utils.logger import get_logger

logger = get_logger(__name__)


class ReflectionResult(BaseModel):
    """反思结果"""
    should_proceed: bool
    risks: List[str]
    suggestions: List[str]
    confidence: float
    reasoning: str
    risk_level: str = "medium"  # low, medium, high, critical


class Reflector:
    """反思器 - 执行前自检"""

    REFLECTION_PROMPT = """你是一个运维操作审查专家。请审查以下操作计划：

## 用户请求
{user_request}

## 计划执行的操作
{planned_actions}

## 操作影响范围
{impact_scope}

请从以下维度评估：

1. **安全性**：是否可能导致数据丢失、服务中断？
2. **必要性**：是否是最优方案？有没有更安全的选择？
3. **可逆性**：操作是否可回滚？
4. **影响范围**：会影响多少用户/服务？

输出 JSON 格式：
{{
    "should_proceed": true/false,
    "risks": ["风险1", "风险2"],
    "suggestions": ["建议1", "建议2"],
    "confidence": 0.0-1.0,
    "reasoning": "详细分析",
    "risk_level": "low/medium/high/critical"
}}
"""

    def __init__(self, llm):
        self.llm = llm
        self.reflection_history = []

    async def reflect(
        self,
        user_request: str,
        planned_actions: List[Dict],
        impact_scope: str = "未知"
    ) -> ReflectionResult:
        """执行反思"""

        # 格式化计划操作
        actions_text = "\n".join([
            f"- {action.get('tool', 'unknown')}: {action.get('args', action.get('params', {}))}"
            for action in planned_actions
        ])

        prompt = self.REFLECTION_PROMPT.format(
            user_request=user_request,
            planned_actions=actions_text,
            impact_scope=impact_scope
        )

        try:
            response = await self.llm.ainvoke(prompt)
            result = self._parse_reflection_result(response.content)

            # 记录历史
            self.reflection_history.append({
                "request": user_request,
                "result": result.dict(),
                "timestamp": str(datetime.now())
            })

            return result

        except Exception as e:
            logger.warning(f"反思失败: {e}，使用默认评估")
            return self._default_reflection(user_request, planned_actions)

    def _parse_reflection_result(self, content: str) -> ReflectionResult:
        """解析反思结果"""
        try:
            # 提取 JSON
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

            result_data = json.loads(json_str)
            return ReflectionResult(**result_data)

        except Exception as e:
            logger.warning(f"解析反思结果失败: {e}")
            raise

    def _default_reflection(self, user_request: str, planned_actions: List[Dict]) -> ReflectionResult:
        """默认反思（基于关键词）"""
        request_lower = user_request.lower()

        # 基于关键词的简单风险评估
        high_risk_keywords = ["delete", "drop", "truncate", "remove", "重启", "restart"]
        critical_keywords = ["数据库", "database", "mysql", "redis", "生产", "production"]

        has_high_risk = any(kw in request_lower for kw in high_risk_keywords)
        has_critical = any(kw in request_lower for kw in critical_keywords)

        if has_high_risk and has_critical:
            return ReflectionResult(
                should_proceed=True,  # 允许执行，但标记高风险
                risks=["涉及生产环境操作", "包含删除/重启操作"],
                suggestions=["建议先在测试环境验证", "准备回滚方案"],
                confidence=0.7,
                reasoning="检测到高风险操作，建议谨慎执行",
                risk_level="high"
            )
        elif has_high_risk:
            return ReflectionResult(
                should_proceed=True,
                risks=["包含修改操作"],
                suggestions=["确认操作参数正确"],
                confidence=0.85,
                reasoning="检测到中等风险操作",
                risk_level="medium"
            )
        else:
            return ReflectionResult(
                should_proceed=True,
                risks=[],
                suggestions=[],
                confidence=0.95,
                reasoning="低风险操作",
                risk_level="low"
            )

    async def check_before_execute(
        self,
        tool_name: str,
        tool_args: dict,
        risk_level: str = "medium"
    ) -> ReflectionResult:
        """执行工具前的快速检查"""

        # 高风险工具必须检查
        if risk_level in ["high", "critical"]:
            return await self.reflect(
                user_request=f"执行 {tool_name}",
                planned_actions=[{"tool": tool_name, "args": tool_args}],
                impact_scope=f"{risk_level} 风险操作"
            )

        # 中低风险快速通过
        return ReflectionResult(
            should_proceed=True,
            risks=[],
            suggestions=[],
            confidence=0.9,
            reasoning=f"{risk_level} 风险操作，直接执行",
            risk_level=risk_level
        )

    def get_reflection_stats(self) -> Dict[str, Any]:
        """获取反思统计"""
        if not self.reflection_history:
            return {"total": 0}

        total = len(self.reflection_history)
        approved = sum(1 for r in self.reflection_history if r["result"]["should_proceed"])
        rejected = total - approved

        risk_levels = {}
        for r in self.reflection_history:
            level = r["result"]["risk_level"]
            risk_levels[level] = risk_levels.get(level, 0) + 1

        return {
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "approval_rate": f"{(approved / total * 100):.1f}%" if total > 0 else "N/A",
            "risk_levels": risk_levels
        }


# 全局单例
_reflector_instance: Optional[Reflector] = None


def get_reflector() -> Reflector:
    """获取反思器单例"""
    from app.core.llm_factory import LLMFactory

    global _reflector_instance
    if _reflector_instance is None:
        llm = LLMFactory.create_llm()
        _reflector_instance = Reflector(llm)
    return _reflector_instance


__all__ = [
    "ReflectionResult",
    "Reflector",
    "get_reflector",
]
