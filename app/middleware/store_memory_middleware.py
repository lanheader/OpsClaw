"""
Store Memory Middleware

直接从 SQLite 主库查询相关知识，动态注入到 system_prompt。
"""

import math
import logging
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain_core.messages import HumanMessage

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class StoreMemoryMiddleware(AgentMiddleware[AgentState, ContextT, ResponseT]):
    """
    从 SQLite 主库动态搜索相关知识注入 system_prompt。

    Args:
        max_tokens: 注入内容的最大 token 数（默认 3000）
        top_k: 最大返回数（默认 5）
        score_threshold: 最低相似度阈值（默认 0.5，基于关键词匹配）
    """

    def __init__(
        self,
        *,
        max_tokens: int = 3000,
        top_k: int = 5,
        score_threshold: float = 0.5,
    ):
        super().__init__()
        self.max_tokens = max_tokens
        self.top_k = top_k
        self.score_threshold = score_threshold

    def _extract_query(self, messages: list[Any]) -> str:
        """从最新用户消息中提取搜索关键词（最多 200 字符）"""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage) and msg.content:
                return str(msg.content)[:200]
        return ""

    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other = len(text) - chinese
        return int(chinese / 1.5 + other / 4)

    def _calculate_score(self, query: str, text: str) -> float:
        """简单的关键词匹配评分"""
        query_lower = query.lower()
        text_lower = text.lower()

        # 提取查询关键词（简单分词）
        keywords = [w for w in query_lower.split() if len(w) > 2]
        if not keywords:
            return 0.0

        # 计算匹配度
        matches = sum(1 for kw in keywords if kw in text_lower)
        return matches / len(keywords)

    def _format_knowledge(self, item: Any) -> str:
        """格式化知识库条目"""
        parts = []
        if item.issue_title:
            parts.append(f"**知识** [{item.category or 'general'}] {item.issue_title[:100]}")
        if item.issue_description:
            parts.append(f"**描述**: {item.issue_description[:200]}")
        if item.symptoms:
            parts.append(f"**症状**: {item.symptoms[:150]}")
        if item.root_cause:
            parts.append(f"**根因**: {item.root_cause[:150]}")
        if item.solution:
            parts.append(f"**解决方案**: {item.solution[:200]}")
        if item.tags:
            parts.append(f"**标签**: {item.tags}")
        return "\n".join(parts)

    def _build_injection(self, results: list[tuple[float, str]]) -> str:
        if not results:
            return ""
        knowledge = [text for _, text in results]
        return "### 相关知识\n" + "\n---\n".join(knowledge)

    def _search_knowledge(self, query: str) -> list[tuple[float, str]]:
        """从 SQLite 主库搜索知识"""
        try:
            from app.models.database import get_db
            from app.models.incident_knowledge import IncidentKnowledgeBase

            db = next(get_db())
            try:
                # 查询活跃的知识库条目
                items = db.query(IncidentKnowledgeBase).filter(
                    IncidentKnowledgeBase.is_active == True  # noqa: E712
                ).all()

                results = []
                total_tokens = 0

                for item in items:
                    # 计算相似度
                    text_to_match = f"{item.issue_title} {item.issue_description} {item.symptoms or ''} {item.root_cause or ''}"
                    score = self._calculate_score(query, text_to_match)

                    if score < self.score_threshold:
                        continue

                    # 格式化文本
                    text = self._format_knowledge(item)
                    tokens = self._estimate_tokens(text)

                    if total_tokens + tokens > self.max_tokens:
                        break

                    results.append((score, text))
                    total_tokens += tokens

                # 按分数排序，取 top_k
                results.sort(key=lambda x: x[0], reverse=True)
                return results[:self.top_k]

            finally:
                db.close()

        except Exception as e:
            logger.warning(f"SQLite 主库搜索失败: {e}")
            return []

    async def awrap_model_call(
        self,
        request: "ModelRequest[ContextT]",
        handler: "Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]]",
    ) -> "ModelResponse[ResponseT]":
        query = self._extract_query(request.messages)
        if not query or len(query.strip()) < 5:
            return await handler(request)

        try:
            results = self._search_knowledge(query)
        except Exception as e:
            logger.warning(f"StoreMemoryMiddleware 搜索失败: {e}")
            return await handler(request)

        if not results:
            return await handler(request)

        injection_text = self._build_injection(results)
        injection = (
            f"<relevant_knowledge>\n"
            f"以下是可能与当前问题相关的历史知识和经验：\n\n"
            f"{injection_text}\n"
            f"</relevant_knowledge>\n\n"
            f"请参考以上知识，但以实际观察到的数据为准。"
        )

        try:
            from deepagents.middleware._utils import append_to_system_message
            new_system = append_to_system_message(request.system_message, injection)
            logger.info(f"🧠 StoreMemoryMiddleware 注入 {len(results)} 条知识")
            return await handler(request.override(system_message=new_system))
        except Exception as e:
            logger.warning(f"StoreMemoryMiddleware 注入失败: {e}")
            return await handler(request)
