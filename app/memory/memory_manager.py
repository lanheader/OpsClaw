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

from app.core.constants import is_incident_handling
from app.utils.logger import get_logger
from app.memory.sqlite_memory_store import SQLiteMemoryStore

logger = get_logger(__name__)

# 触发摘要生成的会话消息数阈值
SUMMARY_TRIGGER_THRESHOLD = 20


class MemoryManager:
    """记忆管理器 - 基于 SQLite FTS5"""

    def __init__(self, user_id: str = None):
        self._user_id = user_id or "default_user"
        self._store = SQLiteMemoryStore()
        logger.info(f"📌 记忆管理器初始化: user_id={self._user_id}, 模式=SQLite FTS5")

    # ==================== 故障记忆 ====================

    async def remember_incident(
        self,
        content: str,
        incident_type: str = "general",
        title: str = None,
        resolution: str = None,
        root_cause: str = None,
        metadata: dict = None
    ) -> str:
        return self._store.store_incident(
            content=content,
            incident_type=incident_type,
            title=title,
            resolution=resolution,
            root_cause=root_cause,
            metadata=metadata,
        )

    async def recall_similar_incidents(
        self,
        query: str,
        top_k: int = 5,
        incident_type: str = None,
        threshold: float = 0.7
    ) -> List[Dict]:
        return self._store.search_incidents(
            query=query,
            top_k=top_k,
            incident_type=incident_type
        )

    # ==================== 知识库 ====================

    async def learn_knowledge(
        self,
        title: str,
        content: str,
        category: str = "general",
        tags: List[str] = None,
        source: str = None,
        metadata: dict = None
    ) -> str:
        return self._store.store_knowledge(
            title=title,
            content=content,
            category=category,
            tags=tags,
            source=source,
            metadata=metadata,
        )

    async def query_knowledge(
        self,
        query: str,
        category: str = None,
        top_k: int = 5,
        threshold: float = 0.7
    ) -> List[Dict]:
        return self._store.search_knowledge(
            query=query,
            category=category,
            top_k=top_k
        )

    # ==================== 会话记忆 ====================

    async def remember_message(
        self,
        session_id: str,
        role: str,
        content: str,
        importance: float = 0.5
    ) -> str:
        # SQLite FTS5 模式下，会话消息由 checkpointer 管理
        # 这里只存储摘要
        return ""

    async def recall_session_context(
        self,
        session_id: str,
        query: str,
        top_k: int = 10
    ) -> List[Dict]:
        # SQLite FTS5 模式下，会话上下文由 checkpointer 的 messages 管理
        return []

    async def summarize_session(
        self,
        session_id: str,
        messages: List[Dict],
        existing_summary: str = None,
    ) -> str:
        """
        为会话生成（增量）摘要，并存储到 FTS5 数据库。
        """
        if not messages:
            return existing_summary or ""

        try:
            from app.core.llm_factory import LLMFactory
            from langchain_core.messages import HumanMessage, SystemMessage

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

            # 存储摘要到 FTS5 数据库（覆盖更新）
            self._store.store_summary(session_id, summary)
            logger.info(f"🧠 会话摘要已生成并存储: session={session_id}, len={len(summary)}")
            return summary

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
            return self._store.get_summary(session_id) or ""
        except Exception as e:
            logger.warning(f"⚠️ 会话摘要检索失败: {e}")
            return ""

    # ==================== 上下文构建 ====================

    async def build_context(
        self,
        user_query: str,
        session_id: str = None,
        include_incidents: bool = True,
        include_knowledge: bool = True,
        include_session: bool = False,
        include_summary: bool = True,
        include_mem0: bool = True,  # 保留参数兼容调用方，忽略
        max_tokens: int = 4500,
        enable_truncation: bool = True,
    ) -> str:
        """构建记忆上下文字符串，注入到用户 prompt"""
        context_parts = []
        current_tokens = 0

        # 扩展查询关键词
        search_query = user_query
        try:
            from app.memory.query_expander import expand_query
            search_query = await expand_query(user_query)
        except Exception as e:
            logger.warning(f"⚠️ 查询扩展失败，使用原始查询: {e}")
            search_query = user_query

        # 优先注入会话摘要（若有），作为长期记忆补充
        if include_summary and session_id:
            try:
                summary = await self.recall_session_summary(session_id)
                if summary:
                    text = self._format_summary(summary)
                    tokens = self._estimate_tokens(text)
                    if current_tokens + tokens <= max_tokens:
                        context_parts.append(text)
                        current_tokens += tokens
            except Exception as e:
                logger.warning(f"⚠️ 会话摘要检索失败: {e}")

        if include_incidents:
            try:
                incidents = await self.recall_similar_incidents(search_query, top_k=3)
                if incidents:
                    text = self._format_incidents(incidents)
                    tokens = self._estimate_tokens(text)
                    if current_tokens + tokens <= max_tokens:
                        context_parts.append(text)
                        current_tokens += tokens
            except Exception as e:
                logger.warning(f"⚠️ 故障记忆检索失败: {e}")

        if include_knowledge:
            try:
                knowledge = await self.query_knowledge(search_query, top_k=3)
                if knowledge:
                    text = self._format_knowledge(knowledge)
                    tokens = self._estimate_tokens(text)
                    if current_tokens + tokens <= max_tokens:
                        context_parts.append(text)
                        current_tokens += tokens
            except Exception as e:
                logger.warning(f"⚠️ 知识库检索失败: {e}")

        if include_session and session_id:
            try:
                contexts = await self.recall_session_context(session_id, user_query, top_k=5)
                if contexts:
                    text = self._format_session_context(contexts)
                    tokens = self._estimate_tokens(text)
                    if current_tokens + tokens <= max_tokens:
                        context_parts.append(text)
                        current_tokens += tokens
            except Exception as e:
                logger.warning(f"⚠️ 会话记忆检索失败: {e}")

        return "\n\n".join(context_parts)

    # ==================== 自动学习 ====================

    async def auto_learn_from_result(
        self,
        user_query: str,
        result: dict,
        session_id: str = None,
        messages: List[Dict] = None,
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
        stats = self._store.get_stats()
        return {"sqlite_fts5": stats, "timestamp": datetime.now().isoformat()}

    # ==================== 内部工具 ====================

    def _format_summary(self, summary: str) -> str:
        return f"## 本次会话摘要\n{summary}"

    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)

    def _format_incidents(self, incidents: List[Dict]) -> str:
        parts = ["## 相关历史故障"]
        for inc in incidents:
            parts.append(f"\n### {inc.get('title') or inc.get('incident_type', '')}")
            parts.append(f"**相似度**: {inc.get('similarity', 0):.0%}")
            parts.append(f"**内容**: {inc.get('content', '')[:200]}")
            if inc.get("resolution"):
                parts.append(f"**解决方案**: {inc['resolution'][:200]}")
            if inc.get("root_cause"):
                parts.append(f"**根本原因**: {inc['root_cause'][:200]}")
        return "\n".join(parts)

    def _format_knowledge(self, knowledge: List[Dict]) -> str:
        parts = ["## 相关知识"]
        for k in knowledge:
            parts.append(f"\n### [{k.get('category', 'general')}] {k.get('title', '')}")
            parts.append(f"**相似度**: {k.get('similarity', 0):.0%}")
            parts.append(f"**内容**: {k.get('content', '')[:300]}")
            if k.get("tags"):
                parts.append(f"**标签**: {', '.join(k['tags'])}")
        return "\n".join(parts)

    def _format_session_context(self, contexts: List[Dict]) -> str:
        parts = ["## 对话历史"]
        for ctx in contexts[:5]:
            parts.append(f"- **{ctx.get('role', '')}**: {ctx.get('content', '')[:150]}")
        return "\n".join(parts)

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
            return last.get("content", "")[:500]
        return str(result.get("output", ""))[:500]

    def _extract_root_cause(self, result: dict) -> str:
        return str(result.get("root_cause") or result.get("diagnosis") or "")[:500]


# 全局单例（按 user_id 隔离）
_instances: Dict[str, MemoryManager] = {}


def get_memory_manager(user_id: str = None) -> MemoryManager:
    user_id = user_id or "default_user"
    if user_id not in _instances:
        _instances[user_id] = MemoryManager(user_id=user_id)
    return _instances[user_id]


__all__ = ["MemoryManager", "get_memory_manager"]
