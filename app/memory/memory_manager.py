"""
记忆管理模块 - 基于 SQLite FTS5 全文搜索

功能：
- 故障记忆管理（运维领域）
- 知识库管理（运维知识）
- 会话记忆管理
- 智能上下文构建

特点：
- 零外部依赖（无需 embedding 模型）
- SQLite FTS5 全文搜索 + BM25 排序
- 支持中英文分词（unicode61 tokenizer）
"""

import os
from typing import List, Dict, Optional, Any
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.constants import is_incident_handling
from app.core.llm_factory import LLMFactory
from app.utils.logger import get_logger
from app.memory.sqlite_fts_store import SQLiteFTSStore, get_langgraph_store

logger = get_logger(__name__)

# 触发摘要生成的会话消息数阈值
SUMMARY_TRIGGER_THRESHOLD = 20


class MemoryManager:
    """记忆管理器 - 基于 SQLite FTS5"""

    def __init__(self, user_id: str = None):  # type: ignore[assignment]
        self._user_id = user_id or "default_user"
        self._store = get_langgraph_store()
        logger.info(f"📌 记忆管理器初始化: user_id={self._user_id}, 模式=SQLite FTS5")

    # ==================== 故障记忆 ====================

    async def remember_incident(
        self,
        content: str,
        incident_type: str = "general",
        title: str = None,  # type: ignore[assignment]
        resolution: str = None,  # type: ignore[assignment]
        root_cause: str = None,  # type: ignore[assignment]
        metadata: dict = None  # type: ignore[assignment]
    ) -> str:
        key = f"incident_{datetime.now().timestamp()}"
        await self._store.aput(
            ("memories", "incidents"),
            key,
            {
                "content": content,
                "title": title or "",
                "incident_type": incident_type,
                "resolution": resolution or "",
                "root_cause": root_cause or "",
                "created_at": datetime.now().isoformat(),
                **(metadata or {}),
            },
        )
        return key

    async def recall_similar_incidents(
        self,
        query: str,
        top_k: int = 5,
        incident_type: str = None,
        threshold: float = 0.5
    ) -> List[Dict]:
        results = await self._store.asearch(("memories", "incidents"), query=query, limit=top_k * 2)
        filtered = []
        for item in results:
            score = item.score or 0.0
            if score >= threshold:
                filtered.append({
                    "id": item.key,
                    "title": item.value.get("title", ""),
                    "content": item.value.get("content", ""),
                    "incident_type": item.value.get("incident_type", ""),
                    "resolution": item.value.get("resolution", ""),
                    "root_cause": item.value.get("root_cause", ""),
                    "similarity": round(score, 3),
                })
        return filtered[:top_k]

    # ==================== 知识库 ====================

    async def learn_knowledge(
        self,
        title: str,
        content: str,
        category: str = "general",
        tags: List[str] = None,  # type: ignore[assignment]
        source: str = None,  # type: ignore[assignment]
        metadata: dict = None  # type: ignore[assignment]
    ) -> str:
        key = f"knowledge_{datetime.now().timestamp()}"
        await self._store.aput(
            ("memories", "knowledge"),
            key,
            {
                "content": content,
                "title": title,
                "category": category,
                "tags": ",".join(tags or []),
                "source": source or "",
                "created_at": datetime.now().isoformat(),
                **(metadata or {}),
            },
        )
        return key

    async def query_knowledge(
        self,
        query: str,
        category: str = None,  # type: ignore[assignment]
        top_k: int = 5,
        threshold: float = 0.5
    ) -> List[Dict]:
        results = await self._store.asearch(("memories", "knowledge"), query=query, limit=top_k * 2)
        filtered = []
        for item in results:
            if (item.score or 0.0) >= threshold:
                filtered.append({
                    "id": item.key,
                    "title": item.value.get("title", ""),
                    "content": item.value.get("content", ""),
                    "category": item.value.get("category", ""),
                    "tags": (item.value.get("tags") or "").split(","),
                    "similarity": round(item.score or 0, 3),
                })
        return filtered[:top_k]

    # ==================== 会话记忆 ====================

    async def summarize_session(
        self,
        session_id: str,
        messages: List[Dict],
        existing_summary: str = None,  # type: ignore[assignment]
    ) -> str:
        """
        为会话生成（增量）摘要，并存储到 FTS5 数据库。
        """
        if not messages:
            return existing_summary or ""

        try:
            llm = LLMFactory.create_llm()

            # 拼接消息文本
            dialogue_text = ""
            for msg in messages:
                role_label = "用户" if msg.get("role") == "user" else "助手"
                content = str(msg.get("content", ""))[:500]
                dialogue_text += f"{role_label}: {content}\n"

            if existing_summary:
                prompt = (
                    f"以下是之前对话的摘要：\n{existing_summary}\n\n"
                    f"以下是新增的对话内容：\n{dialogue_text}\n\n"
                    "请在原有摘要基础上，将新增内容合并，生成一份简洁的增量摘要（不超过500字），"
                    "重点保留关键决策、故障信息和操作结果。"
                )
            else:
                prompt = (
                    f"请为以下对话生成简洁摘要（不超过500字），"
                    f"重点保留关键决策、故障信息和操作结果：\n\n{dialogue_text}"
                )

            response = await llm.ainvoke([
                SystemMessage(content="你是一个运维助手，负责生成对话摘要。"),
                HumanMessage(content=prompt),
            ])
            summary = response.content.strip()

            # 存储摘要到 FTS5 Store（覆盖更新）
            await self._store.aput(
                ("memories", "sessions"),
                f"summary_{session_id}",
                {
                    "content": summary,
                    "session_id": session_id,
                    "updated_at": datetime.now().isoformat(),
                },
            )
            logger.info(f"🧠 会话摘要已生成并存储: session={session_id}, len={len(summary)}")
            return summary  # type: ignore[no-any-return]

        except Exception as e:
            logger.warning(f"⚠️ 会话摘要生成失败: {e}")
            return existing_summary or ""

    async def recall_session_summary(
        self,
        session_id: str,
        top_k: int = 1,
    ) -> str:
        """
        检索最近的会话摘要。
        """
        try:
            results = await self._store.asearch(
                ("memories", "sessions"),
                query=f"summary_{session_id}",
                limit=1
            )
            return results[0].value.get("content", "") if results else ""
        except Exception as e:
            logger.warning(f"⚠️ 会话摘要检索失败: {e}")
            return ""

    # ==================== 自动学习 ====================

    async def auto_learn_from_result(  # type: ignore[no-untyped-def]
        self,
        user_query: str,
        result: dict,
        session_id: str = None,  # type: ignore[assignment]
        messages: List[Dict] = None,  # type: ignore[assignment]
    ):
        """从执行结果自动学习故障处理记录"""
        # 过滤无意义消息
        if len(user_query.strip()) < 10:
            return
        skip_phrases = {"/new", "/help", "你好", "谢谢", "好的", "嗯嗯", "嗯", "哈哈", "收到", "了解"}
        if user_query.strip() in skip_phrases:
            return

        if not is_incident_handling(user_query):
            return

        incident_type = self._detect_incident_type(user_query)
        title = user_query[:100]
        resolution = self._extract_resolution(result)
        root_cause = self._extract_root_cause(result)

        try:
            await self.remember_incident(
                content=user_query,
                incident_type=incident_type,
                title=title,
                resolution=resolution,
                root_cause=root_cause,
                metadata={
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat(),
                },
            )
            logger.info(f"🤖 自动学习故障处理: {title[:50]}")
        except Exception as e:
            logger.warning(f"⚠️ 自动学习失败: {e}")

    # ==================== 统计 ====================

    async def get_stats(self) -> Dict[str, Any]:
        # Store API 不直接提供统计，返回基本信息
        return {
            "backend": "SQLiteFTSStore",
            "timestamp": datetime.now().isoformat(),
            "note": "使用 LangGraph Store API，统计功能由 Store 内部管理"
        }

    # ==================== 内部工具 ====================

    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)

    def _detect_incident_type(self, query: str) -> str:
        q = query.lower()
        if any(k in q for k in ["k8s", "kubernetes", "pod", "容器", "deployment"]):
            return "kubernetes"
        if any(k in q for k in ["mysql", "redis", "postgres", "mongodb", "数据库"]):
            return "database"
        if any(k in q for k in ["nginx", "服务", "接口", "api", "http"]):
            return "service"
        if any(k in q for k in ["磁盘", "内存", "cpu", "资源"]):
            return "resource"
        return "general"

    def _extract_resolution(self, result: dict) -> str:
        if "messages" in result:
            last = result["messages"][-1]
            return last.get("content", "")[:500]  # type: ignore[no-any-return]
        return str(result.get("output", ""))[:500]

    def _extract_root_cause(self, result: dict) -> str:
        return str(result.get("root_cause") or result.get("diagnosis") or "")[:500]


# 全局单例（按 user_id 隔离）
_instances: Dict[str, MemoryManager] = {}


def get_memory_manager(user_id: str = None) -> MemoryManager:  # type: ignore[assignment]
    user_id = user_id or "default_user"
    if user_id not in _instances:
        _instances[user_id] = MemoryManager(user_id=user_id)
    return _instances[user_id]


__all__ = ["MemoryManager", "get_memory_manager"]
