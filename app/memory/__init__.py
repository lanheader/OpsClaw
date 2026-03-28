"""
记忆模块 - SQLite FTS5 记忆存储和管理

功能：
- 故障记忆管理
- 知识库管理
- 会话记忆管理
- 智能上下文构建
- LangGraph Store 适配器（用于 DeepAgents 原生记忆集成）

存储方式：SQLite FTS5 全文搜索（零外部依赖）
- BM25 排序算法
- 支持中英文分词（unicode61 tokenizer）
- 轻量级、可靠、高性能
"""

from typing import Optional

from app.memory.memory_manager import MemoryManager, get_memory_manager
from app.memory.sqlite_fts_store import SQLiteFTSStore

# 全局 Store 实例（延迟初始化）
_store_instance: Optional[SQLiteFTSStore] = None


def get_langgraph_store() -> SQLiteFTSStore:
    """
    获取 LangGraph Store 适配器

    使用 SQLite FTS5 全文搜索，零外部依赖
    """
    global _store_instance

    if _store_instance is not None:
        return _store_instance

    _store_instance = SQLiteFTSStore()
    return _store_instance


__all__ = [
    "MemoryManager",
    "get_memory_manager",
    "SQLiteFTSStore",
    "get_langgraph_store",
]
