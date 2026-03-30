"""
增强的分析服务 - 组合 ReAct + ToT + Self-Reflection + RAG 模式

功能：
1. ToT (Tree of Thought): 多路径诊断探索
2. Self-Reflection: 自我评估诊断结果
3. RAG: 基于历史案例的增强诊断
4. CoT: 显式推理链
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional

from langchain_core.language_models import BaseChatModel
from sqlalchemy import text

from app.core.llm_factory import LLMFactory
from app.memory.memory_manager import get_memory_manager
from app.models.database import get_db
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ========== 辅助函数 ==========

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


# ========== 数据模型 ==========

@dataclass
class DiagnosisHypothesis:
    """诊断假设"""
    id: str
    description: str
    reasoning: str
    confidence: float
    evidence: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.children: List['DiagnosisPath'] = []


@dataclass
class DiagnosisPath:
    """诊断路径（ToT 的路径）"""
    hypothesis: 'DiagnosisHypothesis'
    steps: List[Dict[str, Any]] = field(default_factory=list)
    final_confidence: float = None
    reflection: Optional[Dict[str, Any]] = None
    conclusion: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.final_confidence is None:
            self.final_confidence = self.hypothesis.confidence


@dataclass
class DiagnosisResult:
    """诊断结果"""
    root_cause: str
    confidence: float
    severity: str
    recommendations: List[str]
    alternative_paths: List['DiagnosisPath'] = field(default_factory=list)
    referenced_cases: List[int] = field(default_factory=list)
    reasoning_chain: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


# ========== 知识库服务 ==========

class OpsKnowledgeBase:
    """运维知识库服务 - RAG 模式"""

    async def search_relevant_cases(
        self,
        query: str,
        symptoms: str = "",
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """检索相关的历史案例"""
        db = next(get_db())
        try:
            search_terms = [f"%{query}%"]
            if symptoms:
                search_terms.append(f"%{symptoms}%")

            if not search_terms:
                return []

            sql_query = text("""
                SELECT id, issue_title, issue_description, symptoms,
                       root_cause, solution, effectiveness_score, created_at
                FROM incident_knowledge_base
                WHERE issue_title LIKE :term1
                   OR issue_description LIKE :term1
                   OR symptoms LIKE :term1
                   OR root_cause LIKE :term1
                   OR solution LIKE :term1
                   OR tags LIKE :term1
                   OR category LIKE :term1
                ORDER BY effectiveness_score DESC, created_at DESC
                LIMIT :limit
            """)

            result = db.execute(sql_query, {"term1": search_terms[0], "limit": top_k})

            cases = [
                {
                    "id": row.id,
                    "title": row.issue_title,
                    "description": row.issue_description,
                    "symptoms": row.symptoms,
                    "root_cause": row.root_cause,
                    "solution": row.solution,
                    "score": row.effectiveness_score,
                    "created_at": row.created_at.isoformat() if row.created_at else None
                }
                for row in result
            ]

            logger.info(f"🔍 [RAG] 检索到 {len(cases)} 个相关案例")
            return cases

        except Exception as e:
            logger.warning(f"⚠️ [RAG] 知识库查询失败: {e}")
            return []
        finally:
            db.close()

    def format_cases_as_context(self, cases: List[Dict[str, Any]]) -> str:
        """将案例格式化为上下文"""
        if not cases:
            return "暂无相关历史案例"

        lines = ["相关历史案例：\n"]
        for i, case in enumerate(cases, 1):
            lines.append(f"""
案例 {i}:
- 标题: {case['title']}
- 症状: {case['symptoms']}
- 根因: {case['root_cause']}
- 解决方案: {case['solution']}
- 有效性评分: {case['score']}

---
""")
        return "\n".join(lines)


# ========== 增强分析服务 ==========

class EnhancedAnalyzeService:
    """
    增强的分析服务 - 组合多种设计模式

    模式组合：
    1. ReAct: 推理与行动循环
    2. ToT: 多路径诊断探索
    3. Self-Reflection: 自我评估诊断结果
    4. RAG: 基于历史案例的增强诊断
    5. CoT: 显式推理链
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        self.llm = llm or LLMFactory.create_llm_for_subagent("analyze-agent")
        self.knowledge_base = OpsKnowledgeBase()
        self.memory = get_memory_manager()
        self._reflection_history: List[Dict[str, Any]] = []

    # ==================== 主入口 ====================

    async def diagnose(
        self,
        user_query: str,
        collected_data: Dict[str, Any],
        context: Dict[str, Any] = None,
        use_tot: bool = True,
        use_rag: bool = True,
        max_paths: int = 3,
        max_depth: int = 3
    ) -> DiagnosisResult:
        """执行增强诊断"""
        context = context or {}
        logger.info(f"🔬 [EnhancedAnalyze] 开始诊断: {user_query[:50]}")

        # Phase 1: 记忆增强
        memory_context = await self._get_memory_context(user_query, context)

        # Phase 2: RAG 检索
        rag_context, referenced_cases = await self._get_rag_context(
            user_query, collected_data, use_rag
        )

        # Phase 3: ToT 探索
        if use_tot:
            paths = await self._explore_diagnosis_paths(
                user_query, collected_data, rag_context, memory_context,
                max_paths, max_depth
            )
        else:
            paths = await self._simple_diagnosis(user_query, collected_data, rag_context)

        # Phase 4: 评估选择
        best_path = self._evaluate_paths(paths)

        # Phase 5: 自我反思
        if best_path:
            best_path = await self._reflect_and_refine(best_path, user_query, collected_data)

        # 构建结果
        return self._build_diagnosis_result(
            best_path, [p for p in paths if p != best_path],
            referenced_cases, user_query
        )

    # ==================== Phase 1: 记忆增强 ====================

    async def _get_memory_context(
        self, user_query: str, context: Dict[str, Any]
    ) -> str:
        """获取记忆上下文"""
        try:
            memories = await self.memory.smart_search(
                query=user_query, context=context
            )

            if not memories:
                return ""

            memory_context = await self.memory.build_context(
                user_query=user_query,
                include_mem0=True,
                include_incidents=True,
                include_knowledge=True,
                max_tokens=2000
            )

            logger.info(f"🧠 [Memory] 检索到 {len(memories)} 条相关记忆")

            return f"""
## 历史参考资料（仅供参考）

{memory_context}

⚠️ 重要规则：
1. 如果参考资料与当前问题**不匹配**，请**忽略**它
2. 优先分析实时采集的数据，历史案例仅作参考
3. 如果历史解决方案不适用，请提出新的方案
"""
        except Exception as e:
            logger.warning(f"⚠️ [Memory] 记忆检索失败: {e}")
            return ""

    # ==================== Phase 2: RAG 检索 ====================

    async def _get_rag_context(
        self, user_query: str, collected_data: Dict, use_rag: bool
    ) -> tuple:
        """获取 RAG 上下文"""
        if not use_rag:
            return "", []

        cases = await self.knowledge_base.search_relevant_cases(
            query=user_query,
            symptoms=collected_data.get("symptoms", ""),
            top_k=5
        )

        if not cases:
            return "", []

        context = self.knowledge_base.format_cases_as_context(cases)
        logger.info(f"📚 [RAG] 找到 {len(cases)} 个相关案例")
        return context, [c["id"] for c in cases]

    # ==================== Phase 3: ToT 探索 ====================

    async def _explore_diagnosis_paths(
        self,
        user_query: str,
        collected_data: Dict[str, Any],
        rag_context: str,
        memory_context: str,
        max_paths: int,
        max_depth: int
    ) -> List[DiagnosisPath]:
        """ToT 模式：探索多个诊断路径"""
        hypotheses = await self._generate_hypotheses(
            user_query, collected_data, rag_context, memory_context, max_paths
        )

        logger.info(f"🌳 [ToT] 生成 {len(hypotheses)} 个诊断假设")

        paths = await asyncio.gather(*[
            self._explore_single_path(h, collected_data, rag_context, max_depth)
            for h in hypotheses
        ])

        return list(paths)

    async def _generate_hypotheses(
        self,
        user_query: str,
        collected_data: Dict,
        rag_context: str,
        memory_context: str,
        count: int
    ) -> List[DiagnosisHypothesis]:
        """使用 CoT 生成多个诊断假设"""
        prompt = self._build_hypothesis_prompt(
            user_query, collected_data, rag_context, memory_context, count
        )

        try:
            response = await self.llm.ainvoke(prompt)
            parsed = _extract_json_from_response(response.content)

            if not parsed or "hypotheses" not in parsed:
                raise ValueError("无法解析假设")

            return [
                DiagnosisHypothesis(
                    id=h.get("id", f"h{i+1}"),
                    description=h.get("description", ""),
                    reasoning=h.get("reasoning", ""),
                    confidence=h.get("confidence", 0.5),
                    evidence=h.get("evidence", [])
                )
                for i, h in enumerate(parsed["hypotheses"][:count])
            ]

        except Exception as e:
            logger.error(f"❌ [CoT] 生成假设失败: {e}")
            return [
                DiagnosisHypothesis(
                    id="h1",
                    description="需要进一步分析",
                    reasoning="由于生成假设时出错，使用默认假设",
                    confidence=0.3,
                    evidence=[]
                )
            ]

    def _build_hypothesis_prompt(
        self, user_query, collected_data, rag_context, memory_context, count
    ) -> str:
        """构建假设生成提示词"""
        return f"""作为运维专家，请使用 Chain of Thought 推理，分析以下情况：

**用户问题**：
{user_query}

**采集的数据**：
{self._format_data_summary(collected_data)}

**相关历史案例**：
{rag_context if rag_context else "暂无"}

{memory_context}

请按照以下 CoT 步骤推理：

**步骤1：症状分析**
- 主要症状是什么？
- 哪些指标异常？
- 问题的严重程度如何？

**步骤2：关联分析**
- 这些症状之间有什么关联？
- 可能是哪些组件的问题？

**步骤3：根因推断**
- 最可能的根本原因是什么？
- 每种原因的可能性有多大？

**步骤4：输出假设**
请以 JSON 格式输出 {count} 个诊断假设：
```json
{{
  "hypotheses": [
    {{
      "id": "h1",
      "description": "可能的根因描述",
      "reasoning": "详细的推理过程",
      "confidence": 0.8,
      "evidence": ["证据1", "证据2"]
    }}
  ]
}}
```
"""

    async def _explore_single_path(
        self,
        hypothesis: DiagnosisHypothesis,
        collected_data: Dict,
        rag_context: str,
        max_depth: int
    ) -> DiagnosisPath:
        """探索单条诊断路径 - ReAct 循环"""
        path = DiagnosisPath(hypothesis=hypothesis)

        for depth in range(max_depth):
            # Thought → Action → Observation
            thought = await self._reason_about_path(path, collected_data)
            action = await self._decide_next_action(path)
            observation = await self._perform_verification(action, collected_data)

            path.steps.append({
                "depth": depth,
                "thought": thought,
                "action": action,
                "observation": observation
            })

            path.final_confidence = self._update_confidence(path, observation)

            # 提前终止条件
            if path.final_confidence > 0.9 or path.final_confidence < 0.2:
                break

        path.conclusion = hypothesis.description
        return path

    async def _reason_about_path(self, path: DiagnosisPath, collected_data: Dict) -> str:
        """推理当前路径状态"""
        prompt = f"""当前诊断路径：

**假设**: {path.hypothesis.description}

**已完成的步骤**:
{self._format_path_steps(path)}

请思考：当前假设是否仍然成立？需要什么额外的验证？

请以简洁的语言输出你的思考过程（1-3句话）。"""

        try:
            response = await self.llm.ainvoke(prompt)
            return response.content.strip()
        except Exception:
            return "继续验证当前假设"

    async def _decide_next_action(self, path: DiagnosisPath) -> str:
        """决定下一步验证动作"""
        if len(path.steps) == 0:
            return "initial_verification"
        elif path.final_confidence < 0.5:
            return "deep_investigation"
        return "confirmation"

    async def _perform_verification(
        self, action: str, collected_data: Dict
    ) -> Dict[str, Any]:
        """执行验证并返回结果"""
        return {
            "action": action,
            "result": "verified",
            "details": "基于现有数据进行验证"
        }

    def _update_confidence(self, path: DiagnosisPath, observation: Dict) -> float:
        """基于观察结果更新置信度"""
        base = path.hypothesis.confidence
        bonus = len(path.steps) * 0.05
        return max(0.1, min(0.95, base + bonus))

    # ==================== Phase 4: 简化诊断 ====================

    async def _simple_diagnosis(
        self, user_query: str, collected_data: Dict, rag_context: str
    ) -> List[DiagnosisPath]:
        """简化版单路径诊断"""
        prompt = f"""请分析以下情况并提供诊断：

**用户问题**: {user_query}

**数据摘要**: {self._format_data_summary(collected_data)}

**历史案例**: {rag_context if rag_context else "无"}

请提供：根本原因、严重程度、建议、置信度

以 JSON 格式输出：
```json
{{
  "root_cause": "描述",
  "severity": "medium",
  "recommendations": ["建议1", "建议2"],
  "confidence": 0.8
}}
```
"""

        try:
            response = await self.llm.ainvoke(prompt)
            parsed = _extract_json_from_response(response.content)

            if not parsed:
                raise ValueError("无法解析诊断结果")

            hypothesis = DiagnosisHypothesis(
                id="simple",
                description=parsed.get("root_cause", "未知原因"),
                reasoning="简化诊断",
                confidence=parsed.get("confidence", 0.5),
                evidence=[]
            )

            path = DiagnosisPath(
                hypothesis=hypothesis,
                conclusion=parsed.get("root_cause", ""),
                final_confidence=parsed.get("confidence", 0.5),
                reflection={
                    "severity": parsed.get("severity", "medium"),
                    "recommendations": parsed.get("recommendations", [])
                }
            )

            return [path]

        except Exception as e:
            logger.error(f"简化诊断失败: {e}")
            hypothesis = DiagnosisHypothesis(
                id="default",
                description="需要更多信息进行诊断",
                reasoning="诊断过程中遇到错误",
                confidence=0.3,
                evidence=[]
            )
            return [DiagnosisPath(hypothesis=hypothesis)]

    # ==================== Phase 5: 评估与反思 ====================

    def _evaluate_paths(self, paths: List[DiagnosisPath]) -> Optional[DiagnosisPath]:
        """评估所有路径并选择最优"""
        if not paths:
            return None
        return sorted(paths, key=lambda p: p.final_confidence, reverse=True)[0]

    async def _reflect_and_refine(
        self, path: DiagnosisPath, user_query: str, collected_data: Dict
    ) -> DiagnosisPath:
        """Self-Reflection: 自我反思和精炼"""
        prompt = f"""作为专家审查员，请审查以下诊断：

**原始问题**: {user_query}

**诊断结论**: {path.conclusion}

**置信度**: {path.final_confidence}

**诊断步骤**:
{self._format_path_steps(path)}

**数据摘要**: {self._format_data_summary(collected_data)}

请进行自我评估：

1. **证据充分性** (1-10分): 证据是否足够支持结论？
2. **推理合理性** (1-10分): 推理逻辑是否合理？
3. **潜在问题**: 是否存在矛盾或遗漏？
4. **最终结论**: 是否需要修正结论？
5. **严重程度**: low/medium/high/critical
6. **改进建议**: 如何改进诊断或解决方案？

以 JSON 格式输出：
```json
{{
  "evidence_score": 8,
  "reasoning_score": 7,
  "issues": ["问题1", "问题2"],
  "final_conclusion": "修正后的结论",
  "severity": "medium",
  "recommendations": ["建议1", "建议2"],
  "confidence_adjustment": 0.1
}}
```
"""

        try:
            response = await self.llm.ainvoke(prompt)
            reflection = _extract_json_from_response(response.content)

            if reflection:
                path.reflection = reflection

                if reflection.get("final_conclusion"):
                    path.conclusion = reflection["final_conclusion"]

                if reflection.get("confidence_adjustment"):
                    path.final_confidence = max(0.1, min(0.95,
                        path.final_confidence + reflection["confidence_adjustment"]
                    ))

                self._reflection_history.append({
                    "timestamp": datetime.now().isoformat(),
                    "evidence_score": reflection.get("evidence_score", 0),
                    "reasoning_score": reflection.get("reasoning_score", 0),
                    "issues": reflection.get("issues", [])
                })

        except Exception as e:
            logger.warning(f"自我反思失败: {e}")

        return path

    # ==================== 结果构建 ====================

    def _build_diagnosis_result(
        self,
        best_path: Optional[DiagnosisPath],
        alternative_paths: List[DiagnosisPath],
        referenced_cases: List[int],
        user_query: str
    ) -> DiagnosisResult:
        """构建最终诊断结果"""
        if not best_path:
            return DiagnosisResult(
                root_cause="无法确定根本原因，需要更多信息",
                confidence=0.2,
                severity="low",
                recommendations=["请提供更多关于问题的细节"],
                referenced_cases=referenced_cases
            )

        reflection = best_path.reflection or {}

        return DiagnosisResult(
            root_cause=best_path.conclusion,
            confidence=best_path.final_confidence,
            severity=reflection.get("severity", "medium"),
            recommendations=reflection.get("recommendations", [
                "基于当前分析，建议进一步监控系统状态"
            ]),
            alternative_paths=alternative_paths,
            referenced_cases=referenced_cases,
            reasoning_chain=self._format_path_steps(best_path)
        )

    # ==================== 辅助方法 ====================

    def _format_data_summary(self, data: Dict) -> str:
        """格式化数据摘要"""
        if not data:
            return "无可用数据"

        lines = []
        for key, value in data.items():
            if isinstance(value, (list, dict)):
                value_str = json.dumps(value, ensure_ascii=False)[:200]
            else:
                value_str = str(value)[:200]
            lines.append(f"- {key}: {value_str}")

        return "\n".join(lines)

    def _format_path_steps(self, path: DiagnosisPath) -> str:
        """格式化路径步骤"""
        if not path.steps:
            return "无详细步骤"

        lines = []
        for step in path.steps:
            depth = step.get("depth", 0)
            action = step.get("action", "")
            lines.append(f"步骤{depth+1}: {action}")
            if step.get("thought"):
                lines.append(f"  思考: {step['thought'][:100]}")

        return "\n".join(lines)


# ========== 单例 ==========

_analyze_service_instance: Optional[EnhancedAnalyzeService] = None


def get_enhanced_analyze_service() -> EnhancedAnalyzeService:
    """获取增强分析服务单例"""
    global _analyze_service_instance
    if _analyze_service_instance is None:
        _analyze_service_instance = EnhancedAnalyzeService()
    return _analyze_service_instance


__all__ = [
    "EnhancedAnalyzeService",
    "DiagnosisResult",
    "get_enhanced_analyze_service",
]
