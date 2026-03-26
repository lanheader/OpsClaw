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
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel

from app.core.llm_factory import LLMFactory
from app.models.database import get_db
from app.utils.logger import get_logger
from app.memory.memory_manager import get_memory_manager

logger = get_logger(__name__)

class DiagnosisHypothesis:
    """诊断假设"""
    def __init__(
        self,
        id: str,
        description: str,
        reasoning: str,
        confidence: float,
        evidence: List[str] = None
    ):
        self.id = id
        self.description = description
        self.reasoning = reasoning
        self.confidence = confidence
        self.evidence = evidence or []
        self.children: List['DiagnosisPath'] = []


class DiagnosisPath:
    """诊断路径（ToT 的路径）"""
    def __init__(
        self,
        hypothesis: DiagnosisHypothesis,
        steps: List[Dict[str, Any]] = None
    ):
        self.hypothesis = hypothesis
        self.steps = steps or []
        self.final_confidence: float = hypothesis.confidence
        self.reflection: Optional[Dict[str, Any]] = None
        self.conclusion: str = ""
        self.metadata: Dict[str, Any] = {}


class DiagnosisResult:
    """诊断结果"""
    def __init__(
        self,
        root_cause: str,
        confidence: float,
        severity: str,
        recommendations: List[str],
        alternative_paths: List[DiagnosisPath] = None,
        referenced_cases: List[int] = None,
        reasoning_chain: str = ""
    ):
        self.root_cause = root_cause
        self.confidence = confidence
        self.severity = severity  # low, medium, high, critical
        self.recommendations = recommendations
        self.alternative_paths = alternative_paths or []
        self.referenced_cases = referenced_cases or []
        self.reasoning_chain = reasoning_chain
        self.metadata: Dict[str, Any] = {}


class OpsKnowledgeBase:
    """
    运维知识库服务 - RAG 模式

    功能：
    1. 存储历史故障案例
    2. 语义检索相关案例
    3. 增强诊断推理
    """

    async def search_relevant_cases(
        self,
        query: str,
        symptoms: str = "",
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        检索相关的历史案例

        Args:
            query: 查询关键词
            symptoms: 症状描述
            top_k: 返回数量

        Returns:
            相关案例列表
        """
        from sqlalchemy import text, or_

        db = next(get_db())
        try:
            # 构建搜索条件
            search_terms = []
            if query:
                search_terms.append(f"%{query}%")
            if symptoms:
                search_terms.append(f"%{symptoms}%")

            if not search_terms:
                return []

            # 简化版：使用 SQL LIKE 查询（支持多字段模糊匹配）
            # TODO: 升级为向量检索（Pinecone, Milvus等）
            # 注意：issue_title 的权重最高，然后是 symptoms，root_cause
            sql_query = text("""
                SELECT
                    id,
                    issue_title,
                    issue_description,
                    symptoms,
                    root_cause,
                    solution,
                    effectiveness_score,
                    created_at
                FROM incident_knowledge_base
                WHERE
                    issue_title LIKE :term1
                    OR issue_description LIKE :term1
                    OR symptoms LIKE :term1
                    OR root_cause LIKE :term1
                    OR solution LIKE :term1
                    OR tags LIKE :term1
                    OR category LIKE :term1
                ORDER BY effectiveness_score DESC, created_at DESC
                LIMIT :limit
            """)

            result = db.execute(
                sql_query,
                {"term1": search_terms[0], "limit": top_k}
            )

            cases = []
            for row in result:
                cases.append({
                    "id": row.id,
                    "title": row.issue_title,
                    "description": row.issue_description,
                    "symptoms": row.symptoms,
                    "root_cause": row.root_cause,
                    "solution": row.solution,
                    "score": row.effectiveness_score,
                    "created_at": row.created_at.isoformat() if row.created_at else None
                })

            logger.info(f"🔍 [RAG] 检索到 {len(cases)} 个相关案例")
            return cases

        except Exception as e:
            logger.warning(f"⚠️ [RAG] 知识库查询失败: {e}")
            return []
        finally:
            db.close()

    def _format_cases_as_context(self, cases: List[Dict[str, Any]]) -> str:
        """将案例格式化为上下文"""
        if not cases:
            return "暂无相关历史案例"

        context = "相关历史案例：\n\n"
        for i, case in enumerate(cases, 1):
            context += f"""
案例 {i}:
- 标题: {case['title']}
- 症状: {case['symptoms']}
- 根因: {case['root_cause']}
- 解决方案: {case['solution']}
- 有效性评分: {case['score']}

---
"""
        return context


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
        self._reflection_history: List[Dict[str, Any]] = []
        # 记忆管理器（参考 OpenClaw 的检索式访问）
        self.memory = get_memory_manager()
        # 记忆管理器（参考 OpenClaw 的检索式访问）
        self.memory = get_memory_manager()

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
        """
        执行增强诊断

        Args:
            user_query: 用户查询
            collected_data: 采集的数据
            context: 上下文信息
            use_tot: 是否使用 ToT 模式
            use_rag: 是否使用 RAG 增强
            max_paths: 最大诊断路径数
            max_depth: 每条路径的最大深度

        Returns:
            诊断结果
        """
        context = context or {}
        logger.info(f"🔬 [EnhancedAnalyze] 开始诊断: {user_query[:50]}")

        # ===== 记忆增强（参考 OpenClaw 的延迟加载）=====
        memory_context = ""
        if self._should_use_memory(user_query):
            try:
                # 1. 使用智能检索（业务层过滤）
                memories = await self.memory.smart_search(
                    query=user_query,
                    context=context
                )
                
                # 2. 如果有记忆，构建上下文
                if memories:
                    memory_context = await self.memory.build_context(
                        user_query=user_query,
                        include_mem0=True,
                        include_incidents=True,
                        include_knowledge=True,
                        max_tokens=2000
                    )

                    memory_context = f"""
## 历史参考资料（仅供参考）

{memory_context}

⚠️ 重要规则：
1. 如果参考资料与当前问题**不匹配**，请**忽略**它
2. 优先分析实时采集的数据，历史案例仅作参考
3. 如果历史解决方案不适用，请提出新的方案
"""
                    logger.info(f"🧠 [Memory] 检索到 {len(memories)} 条相关记忆")
            except Exception as e:
                logger.warning(f"⚠️ [Memory] 记忆检索失败: {e}")

        # Phase 1: RAG - 检索相关案例
        referenced_cases = []
        rag_context = ""
        if use_rag:
            relevant_cases = await self.knowledge_base.search_relevant_cases(
                query=user_query,
                symptoms=collected_data.get("symptoms", ""),
                top_k=5
            )
            if relevant_cases:
                referenced_cases = [c["id"] for c in relevant_cases]
                rag_context = self.knowledge_base._format_cases_as_context(relevant_cases)
                logger.info(f"📚 [RAG] 找到 {len(referenced_cases)} 个相关案例")

        # Phase 2: ToT - 生成并探索多个诊断假设
        if use_tot:
            paths = await self._explore_diagnosis_paths(
                user_query=user_query,
                collected_data=collected_data,
                rag_context=rag_context,
                max_paths=max_paths,
                max_depth=max_depth
            )
        else:
            # 单路径诊断（简化版）
            paths = await self._simple_diagnosis(
                user_query=user_query,
                collected_data=collected_data,
                rag_context=rag_context
            )

        # Phase 3: 评估并选择最优路径
        best_path = await self._evaluate_paths(paths)

        # Phase 4: 自我反思与验证
        if best_path:
            best_path = await self._reflect_and_refine(
                path=best_path,
                user_query=user_query,
                collected_data=collected_data
            )

        # 构建最终结果
        result = await self._build_diagnosis_result(
            best_path=best_path,
            alternative_paths=[p for p in paths if p != best_path],
            referenced_cases=referenced_cases,
            user_query=user_query,
            collected_data=collected_data
        )

        logger.info(f"✅ [EnhancedAnalyze] 诊断完成: {result.root_cause[:50]}... (置信度: {result.confidence})")
        return result

    async def _explore_diagnosis_paths(
        self,
        user_query: str,
        collected_data: Dict[str, Any],
        rag_context: str,
        max_paths: int,
        max_depth: int
    ) -> List[DiagnosisPath]:
        """
        ToT 模式：探索多个诊断路径

        1. 生成多个诊断假设
        2. 并行探索各路径
        3. 返回所有路径结果
        """
        # Step 1: 生成多个诊断假设
        hypotheses = await self._generate_hypotheses(
            user_query=user_query,
            collected_data=collected_data,
            rag_context=rag_context,
            count=max_paths
        )

        logger.info(f"🌳 [ToT] 生成 {len(hypotheses)} 个诊断假设")

        # Step 2: 并行探索各路径
        paths = await asyncio.gather(*[
            self._explore_single_path(
                hypothesis=h,
                collected_data=collected_data,
                rag_context=rag_context,
                max_depth=max_depth
            )
            for h in hypotheses
        ])

        return list(paths)

    async def _generate_hypotheses(
        self,
        user_query: str,
        collected_data: Dict[str, Any],
        rag_context: str,
        count: int
    ) -> List[DiagnosisHypothesis]:
        """
        使用 CoT 生成多个诊断假设

        CoT 推理过程：
        1. 分析症状
        2. 识别关键指标
        3. 推导可能根因
        4. 评估置信度
        """
        data_summary = self._format_data_summary(collected_data)

        prompt = f"""作为运维专家，请使用 Chain of Thought 推理，分析以下情况：

**用户问题**：
{user_query}

**采集的数据**：
{data_summary}

**相关历史案例**：
{rag_context if rag_context else "暂无"}

请按照以下 CoT 步骤推理：

**步骤1：症状分析**
- 主要症状是什么？
- 哪些指标异常？
- 问题的严重程度如何？

**步骤2：关联分析**
- 这些症状之间有什么关联？
- 可能是哪些组件的问题？
- 上下游依赖关系是什么？

**步骤3：根因推断**
- 最可能的根本原因是什么？
- 有哪些可能的次要原因？
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

注意：
- 请生成 {count} 个不同的假设
- 假设之间应该有差异（不同的根因方向）
- 置信度应该是相对的（总和接近1）
"""

        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content

            # 解析 JSON
            # 尝试提取 JSON 部分
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
            elif "```" in content:
                json_start = content.find("```") + 3
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
            else:
                # 尝试找到最外层的 { }
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    json_str = content[start:end]
                else:
                    json_str = content

            parsed = json.loads(json_str)

            hypotheses = []
            for h in parsed.get("hypotheses", [])[:count]:
                hypotheses.append(DiagnosisHypothesis(
                    id=h.get("id", f"h{len(hypotheses)+1}"),
                    description=h.get("description", ""),
                    reasoning=h.get("reasoning", ""),
                    confidence=h.get("confidence", 0.5),
                    evidence=h.get("evidence", [])
                ))

            return hypotheses

        except Exception as e:
            logger.error(f"❌ [CoT] 生成假设失败: {e}")
            # 返回默认假设
            return [
                DiagnosisHypothesis(
                    id="h1",
                    description="需要进一步分析",
                    reasoning="由于生成假设时出错，使用默认假设",
                    confidence=0.3,
                    evidence=[]
                )
            ]

    async def _explore_single_path(
        self,
        hypothesis: DiagnosisHypothesis,
        collected_data: Dict[str, Any],
        rag_context: str,
        max_depth: int
    ) -> DiagnosisPath:
        """
        探索单条诊断路径 - ReAct 循环

        每一步：Thought → Action → Observation
        """
        path = DiagnosisPath(hypothesis=hypothesis)

        for depth in range(max_depth):
            # Thought: 基于当前状态思考
            thought = await self._reason_about_path(path, collected_data, rag_context)

            # Action: 决定下一步验证
            action = await self._decide_next_action(path, collected_data)

            # Observation: 执行验证并获取结果
            observation = await self._perform_verification(action, collected_data)

            # 记录步骤
            path.steps.append({
                "depth": depth,
                "thought": thought,
                "action": action,
                "observation": observation
            })

            # 更新置信度
            path.final_confidence = await self._update_confidence(path, observation)

            # 检查是否应该提前终止
            if path.final_confidence > 0.9 or path.final_confidence < 0.2:
                break

        # 设置初步结论
        path.conclusion = hypothesis.description

        return path

    async def _reason_about_path(
        self,
        path: DiagnosisPath,
        collected_data: Dict[str, Any],
        rag_context: str
    ) -> str:
        """推理当前路径状态"""
        steps_summary = self._format_path_steps(path)

        prompt = f"""当前诊断路径：

**假设**: {path.hypothesis.description}

**已完成的步骤**:
{steps_summary}

**数据摘要**:
{self._format_data_summary(collected_data)}

请思考：
1. 当前假设是否仍然成立？
2. 需要什么额外的验证？
3. 置信度应该调整吗？

请以简洁的语言输出你的思考过程（1-3句话）。"""

        try:
            response = await self.llm.ainvoke(prompt)
            return response.content.strip()
        except Exception as e:
            logger.warning(f"推理失败: {e}")
            return "继续验证当前假设"

    async def _decide_next_action(
        self,
        path: DiagnosisPath,
        collected_data: Dict[str, Any]
    ) -> str:
        """决定下一步验证动作"""
        # 简化版：返回验证类型
        if len(path.steps) == 0:
            return "initial_verification"
        elif path.final_confidence < 0.5:
            return "deep_investigation"
        else:
            return "confirmation"

    async def _perform_verification(
        self,
        action: str,
        collected_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行验证并返回结果"""
        # 简化版：基于已有数据进行验证
        # 实际实现中可以调用工具进行额外验证

        return {
            "action": action,
            "result": "verified",
            "details": "基于现有数据进行验证"
        }

    async def _update_confidence(
        self,
        path: DiagnosisPath,
        observation: Dict[str, Any]
    ) -> float:
        """基于观察结果更新置信度"""
        # 简化版：根据步骤数量微调置信度
        base_confidence = path.hypothesis.confidence
        step_bonus = len(path.steps) * 0.05

        new_confidence = min(0.95, base_confidence + step_bonus)
        return max(0.1, new_confidence)

    async def _simple_diagnosis(
        self,
        user_query: str,
        collected_data: Dict[str, Any],
        rag_context: str
    ) -> List[DiagnosisPath]:
        """简化版单路径诊断（当不使用 ToT 时）"""
        prompt = f"""请分析以下情况并提供诊断：

**用户问题**: {user_query}

**数据摘要**: {self._format_data_summary(collected_data)}

**历史案例**: {rag_context if rag_context else "无"}

请提供：
1. 根本原因
2. 严重程度（low/medium/high/critical）
3. 建议
4. 置信度（0-1）

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

            parsed = json.loads(json_str)

            # 创建单路径
            hypothesis = DiagnosisHypothesis(
                id="simple",
                description=parsed.get("root_cause", "未知原因"),
                reasoning="简化诊断",
                confidence=parsed.get("confidence", 0.5),
                evidence=[]
            )

            path = DiagnosisPath(hypothesis=hypothesis)
            path.conclusion = parsed.get("root_cause", "")
            path.final_confidence = parsed.get("confidence", 0.5)
            path.reflection = {
                "severity": parsed.get("severity", "medium"),
                "recommendations": parsed.get("recommendations", [])
            }

            return [path]

        except Exception as e:
            logger.error(f"简化诊断失败: {e}")
            # 返回默认路径
            hypothesis = DiagnosisHypothesis(
                id="default",
                description="需要更多信息进行诊断",
                reasoning="诊断过程中遇到错误",
                confidence=0.3,
                evidence=[]
            )
            return [DiagnosisPath(hypothesis=hypothesis)]

    async def _evaluate_paths(
        self,
        paths: List[DiagnosisPath]
    ) -> Optional[DiagnosisPath]:
        """评估所有路径并选择最优"""
        if not paths:
            return None

        # 按置信度排序
        sorted_paths = sorted(paths, key=lambda p: p.final_confidence, reverse=True)
        return sorted_paths[0]

    async def _reflect_and_refine(
        self,
        path: DiagnosisPath,
        user_query: str,
        collected_data: Dict[str, Any]
    ) -> DiagnosisPath:
        """
        Self-Reflection: 自我反思和精炼诊断结果
        """
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

            reflection = json.loads(json_str)

            # 更新路径
            path.reflection = reflection

            if reflection.get("final_conclusion"):
                path.conclusion = reflection["final_conclusion"]

            if reflection.get("confidence_adjustment"):
                path.final_confidence = max(0.1, min(0.95,
                    path.final_confidence + reflection["confidence_adjustment"]
                ))

            # 记录反思历史
            self._reflection_history.append({
                "timestamp": datetime.now().isoformat(),
                "original_confidence": path.final_confidence - reflection.get("confidence_adjustment", 0),
                "evidence_score": reflection.get("evidence_score", 0),
                "reasoning_score": reflection.get("reasoning_score", 0),
                "issues": reflection.get("issues", [])
            })

        except Exception as e:
            logger.warning(f"自我反思失败: {e}")

        return path

    async def _build_diagnosis_result(
        self,
        best_path: Optional[DiagnosisPath],
        alternative_paths: List[DiagnosisPath],
        referenced_cases: List[int],
        user_query: str,
        collected_data: Dict[str, Any]
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

    def _format_data_summary(self, data: Dict[str, Any]) -> str:
        """格式化数据摘要"""
        if not data:
            return "无可用数据"

        summary_parts = []
        for key, value in data.items():
            if isinstance(value, (list, dict)):
                value_str = json.dumps(value, ensure_ascii=False)[:200]
            else:
                value_str = str(value)[:200]
            summary_parts.append(f"- {key}: {value_str}")

        return "\n".join(summary_parts)

    def _format_path_steps(self, path: DiagnosisPath) -> str:
        """格式化路径步骤"""
        if not path.steps:
            return "无详细步骤"

        lines = []
        for step in path.steps:
            depth = step.get("depth", 0)
            thought = step.get("thought", "")[:100]
            action = step.get("action", "")
            lines.append(f"步骤{depth+1}: {action}")
            if thought:
                lines.append(f"  思考: {thought}")

        return "\n".join(lines)


_analyze_service_instance: Optional[EnhancedAnalyzeService] = None


def get_enhanced_analyze_service() -> EnhancedAnalyzeService:
    """获取增强分析服务单例"""
    global _analyze_service_instance
    if _analyze_service_instance is None:
        _analyze_service_instance = EnhancedAnalyzeService()
    return _analyze_service_instance



    
def _should_use_memory(self, query: str) -> bool:
    """
    判断是否需要使用记忆（参考 OpenClaw）

    规则：
    - 故障诊断 → 使用记忆
    - 其他查询 → 使用记忆

    Args:
        query: 用户查询

    Returns:
        是否需要使用记忆
    """
    # 分析诊断默认使用记忆
    return True

__all__ = [
    "EnhancedAnalyzeService",
    "DiagnosisResult",
    "get_enhanced_analyze_service",
]
