"""
SQLite FTS5 适配器 - 实现 LangGraph BaseStore 接口

零外部依赖的记忆存储方案：
- 基于 SQLite FTS5 全文搜索
- 无需 embedding 模型
- 使用 BM25 排序算法
- 支持中英文分词（unicode61 tokenizer）

参考：https://langchain-ai.github.io/langgraph/reference/store/#langgraph.store.base.BaseStore
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import TYPE_CHECKING, Any, Iterable, Literal, Optional, Union

from langgraph.store.base import (
    BaseStore,
    Item,
    NamespacePath,
    NOT_PROVIDED,
    NotProvided,
    Op,
    Result,
    SearchItem,
)

from app.core.config import get_settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# 线程池执行器（用于同步方法调用异步实现）
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sqlite_fts_store_")


def _run_async(coro):
    """
    在同步上下文中安全运行异步协程

    处理三种情况：
    1. 没有运行的事件循环 - 直接使用 asyncio.run()
    2. 有运行的事件循环（同一线程）- 使用 ThreadPoolExecutor
    3. 有运行的事件循环（不同线程）- 使用 asyncio.run_coroutine_threadsafe()
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 没有运行的事件循环
        return asyncio.run(coro)

    # 有运行的事件循环，需要在另一个线程中运行
    future = _executor.submit(asyncio.run, coro)
    return future.result()


class SQLiteFTSStore(BaseStore):
    """
    SQLite FTS5 适配器 - 实现 LangGraph BaseStore 接口

    特点：
    - 零外部依赖（无需 embedding 模型）
    - 使用 FTS5 全文搜索 + BM25 排序
    - 支持中英文分词（unicode61 tokenizer）
    - 轻量级、可靠、高性能

    命名空间映射：
    - ("memories", "incidents") -> incidents 表
    - ("memories", "knowledge") -> knowledge 表
    - ("memories", "sessions") -> sessions 表

    支持的操作：
    - put/aput: 存储数据
    - get/aget: 获取数据
    - delete/adelete: 删除数据
    - search/asearch: 关键词搜索（FTS5）
    - list_namespaces/alist_namespaces: 列出命名空间
    - batch/abatch: 批量操作
    """

    # 预定义的命名空间
    PREDEFINED_NAMESPACES = [
        ("memories", "incidents"),
        ("memories", "knowledge"),
        ("memories", "sessions"),
    ]

    def __init__(self, db_path: str = None):
        """
        初始化 SQLite FTS5 存储适配器

        Args:
            db_path: 数据库路径，默认使用配置中的路径
        """
        if db_path is None:
            settings = get_settings()
            db_path = getattr(settings, "MEMORY_DB_PATH", "./workspace/data/memory_fts.db")

        # 确保目录存在
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.db_path = db_path
        self._init_tables()
        logger.info(f"✅ SQLiteFTSStore 适配器初始化完成 | {db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        """初始化数据库表"""
        with self._get_connection() as conn:
            # 故障记忆表（FTS5）
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS incidents_fts
                USING fts5(
                    key, namespace, content, title, incident_type,
                    resolution, root_cause, metadata,
                    tokenize='unicode61'
                )
            """)

            # 知识库表（FTS5）
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
                USING fts5(
                    key, namespace, content, title, category,
                    tags, source, metadata,
                    tokenize='unicode61'
                )
            """)

            # 会话记忆表（FTS5）
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts
                USING fts5(
                    key, namespace, content, session_id, metadata,
                    tokenize='unicode61'
                )
            """)

            # 元数据表（存储时间戳等非搜索字段）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS items_meta (
                    key TEXT PRIMARY KEY,
                    namespace TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

            conn.commit()

    # ==================== 内部辅助方法 ====================

    @staticmethod
    def _row_get(row: sqlite3.Row, key: str, default: Any = None) -> Any:
        """
        安全地从 sqlite3.Row 获取值

        Args:
            row: 数据库行
            key: 键名
            default: 默认值

        Returns:
            值或默认值
        """
        try:
            return row[key]
        except (KeyError, IndexError):
            return default

    def _namespace_to_table(self, namespace: tuple[str, ...]) -> str:
        """
        将命名空间映射到表名

        Args:
            namespace: 命名空间元组

        Returns:
            表名
        """
        if not namespace:
            return "knowledge_fts"

        if namespace[0] == "memories" and len(namespace) >= 2:
            if namespace[1] == "incidents":
                return "incidents_fts"
            elif namespace[1] == "knowledge":
                return "knowledge_fts"
            elif namespace[1] == "sessions":
                return "sessions_fts"

        return "knowledge_fts"

    def _escape_fts_query(self, query: str) -> str:
        """
        转义 FTS5 特殊字符，构建安全查询

        FTS5 特殊字符: " * ( ) ^ # : - |
        空查询返回空字符串（调用方会跳过 MATCH）

        Args:
            query: 原始查询字符串

        Returns:
            转义后的 FTS5 查询
        """
        if not query or not query.strip():
            return ""

        # 移除 FTS5 特殊运算符字符（这些字符在 FTS5 中有特殊含义）
        cleaned = re.sub(r'[*()^#:|\-]', ' ', query)

        # 转义双引号
        cleaned = cleaned.replace('"', '""')

        # 将空格/逗号分隔的词转为 OR 查询
        terms = [
            f'"{t.strip()}"'
            for t in re.split(r'[\s,;，；]+', cleaned)
            if t.strip()
        ]

        return " OR ".join(terms) if terms else ""

    def _build_item(
        self,
        row: sqlite3.Row,
        namespace: tuple[str, ...],
    ) -> Optional[Item]:
        """
        从数据库行构建 Item 对象

        Args:
            row: 数据库行
            namespace: 命名空间

        Returns:
            Item 对象
        """
        try:
            key = row["key"]
            content = row["content"]
            metadata_str = self._row_get(row, "metadata", "{}")

            # 解析元数据
            try:
                extra_meta = json.loads(metadata_str) if metadata_str else {}
            except json.JSONDecodeError:
                extra_meta = {}

            # 获取时间戳
            created_at_str = extra_meta.get("created_at", datetime.now().isoformat())
            updated_at_str = extra_meta.get("updated_at", created_at_str)

            try:
                created_at = datetime.fromisoformat(created_at_str)
            except (ValueError, TypeError):
                created_at = datetime.now()

            try:
                updated_at = datetime.fromisoformat(updated_at_str)
            except (ValueError, TypeError):
                updated_at = created_at

            # 构建值字典
            value = {"content": content}
            value.update(extra_meta)

            return Item(
                value=value,
                key=key,
                namespace=namespace,
                created_at=created_at,
                updated_at=updated_at,
            )
        except Exception as e:
            logger.warning(f"构建 Item 失败: {e}")
            return None

    # ==================== 异步方法 ====================

    async def aput(
        self,
        namespace: tuple[str, ...],
        key: str,
        value: dict[str, Any],
        index: Literal[False] | list[str] | None = None,
        *,
        ttl: float | None | NotProvided = NOT_PROVIDED,
    ) -> None:
        """
        异步存储数据

        Args:
            namespace: 命名空间
            key: 数据键
            value: 数据值
            index: 索引配置（暂不支持）
            ttl: 生存时间（秒），暂不支持
        """
        table = self._namespace_to_table(namespace)
        content = value.get("content", str(value))
        namespace_str = "/".join(namespace) if namespace else ""

        # 构建元数据
        now = datetime.now()
        metadata = {
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        # 添加额外元数据（排除复杂类型）
        for k, v in value.items():
            if k == "content":
                continue
            if isinstance(v, (dict, list)):
                continue
            metadata[k] = str(v) if not isinstance(v, str) else v

        metadata_str = json.dumps(metadata, ensure_ascii=False)

        try:
            with self._get_connection() as conn:
                # 先删除旧记录（如果存在）
                conn.execute(f"DELETE FROM {table} WHERE key = ?", [key])

                # 根据表类型插入数据
                if table == "incidents_fts":
                    conn.execute(
                        f"""
                        INSERT INTO {table}
                        (key, namespace, content, title, incident_type, resolution, root_cause, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            key,
                            namespace_str,
                            content,
                            value.get("title", ""),
                            value.get("incident_type", ""),
                            value.get("resolution", ""),
                            value.get("root_cause", ""),
                            metadata_str,
                        ],
                    )
                elif table == "knowledge_fts":
                    conn.execute(
                        f"""
                        INSERT INTO {table}
                        (key, namespace, content, title, category, tags, source, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            key,
                            namespace_str,
                            content,
                            value.get("title", ""),
                            value.get("category", ""),
                            value.get("tags", ""),
                            value.get("source", ""),
                            metadata_str,
                        ],
                    )
                else:  # sessions_fts
                    conn.execute(
                        f"""
                        INSERT INTO {table}
                        (key, namespace, content, session_id, metadata)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        [
                            key,
                            namespace_str,
                            content,
                            value.get("session_id", ""),
                            metadata_str,
                        ],
                    )

                # 更新元数据表
                conn.execute(
                    """
                    INSERT OR REPLACE INTO items_meta (key, namespace, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    [key, namespace_str, now.isoformat(), now.isoformat()],
                )

                conn.commit()

            logger.debug(f"💾 SQLiteFTSStore.aput: key={key}, namespace={namespace}")

        except Exception as e:
            logger.error(f"SQLiteFTSStore.aput 失败: {e}")
            raise

    async def aget(
        self,
        namespace: tuple[str, ...],
        key: str,
        *,
        refresh_ttl: bool | None = None,
    ) -> Optional[Item]:
        """
        异步获取数据

        Args:
            namespace: 命名空间
            key: 数据键
            refresh_ttl: 是否刷新 TTL（暂不支持）

        Returns:
            Item 或 None
        """
        table = self._namespace_to_table(namespace)

        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    f"SELECT * FROM {table} WHERE key = ?",
                    [key],
                ).fetchone()

                if row:
                    return self._build_item(row, namespace)

        except Exception as e:
            logger.debug(f"SQLiteFTSStore.aget: key={key} not found: {e}")

        return None

    async def adelete(
        self,
        namespace: tuple[str, ...],
        key: str,
    ) -> None:
        """
        异步删除数据

        Args:
            namespace: 命名空间
            key: 数据键
        """
        table = self._namespace_to_table(namespace)

        try:
            with self._get_connection() as conn:
                conn.execute(f"DELETE FROM {table} WHERE key = ?", [key])
                conn.execute("DELETE FROM items_meta WHERE key = ?", [key])
                conn.commit()

            logger.debug(f"🗑️ SQLiteFTSStore.adelete: key={key}")

        except Exception as e:
            logger.warning(f"SQLiteFTSStore.adelete failed: {e}")

    async def asearch(
        self,
        namespace_prefix: tuple[str, ...],
        /,
        *,
        query: Optional[str] = None,
        filter: Optional[dict[str, Any]] = None,
        limit: int = 10,
        offset: int = 0,
        refresh_ttl: bool | None = None,
    ) -> list[SearchItem]:
        """
        异步关键词搜索（FTS5）

        Args:
            namespace_prefix: 命名空间前缀（位置参数）
            query: 搜索查询（关键词搜索）
            filter: 过滤条件
            limit: 返回数量限制
            offset: 偏移量
            refresh_ttl: 是否刷新 TTL（暂不支持）

        Returns:
            SearchItem 列表
        """
        table = self._namespace_to_table(namespace_prefix)
        items = []

        try:
            with self._get_connection() as conn:
                if query:
                    # FTS5 全文搜索
                    fts_query = self._escape_fts_query(query)

                    # 如果转义后为空，回退到无查询模式
                    if not fts_query:
                        sql = f"""
                            SELECT * FROM {table}
                            LIMIT ? OFFSET ?
                        """
                        rows = conn.execute(sql, [limit, offset]).fetchall()
                    else:
                        # 使用 BM25 排序
                        sql = f"""
                            SELECT *, bm25({table}) as rank
                            FROM {table}
                            WHERE {table} MATCH ?
                            ORDER BY rank
                            LIMIT ? OFFSET ?
                        """
                        rows = conn.execute(sql, [fts_query, limit, offset]).fetchall()
                else:
                    # 无查询，返回所有数据
                    sql = f"""
                        SELECT * FROM {table}
                        LIMIT ? OFFSET ?
                    """

                    rows = conn.execute(sql, [limit, offset]).fetchall()

                for row in rows:
                    try:
                        key = row["key"]
                        content = row["content"]
                        metadata_str = self._row_get(row, "metadata", "{}")

                        try:
                            extra_meta = json.loads(metadata_str) if metadata_str else {}
                        except json.JSONDecodeError:
                            extra_meta = {}

                        # 获取时间戳
                        created_at_str = extra_meta.get(
                            "created_at", datetime.now().isoformat()
                        )
                        updated_at_str = extra_meta.get("updated_at", created_at_str)

                        try:
                            created_at = datetime.fromisoformat(created_at_str)
                        except (ValueError, TypeError):
                            created_at = datetime.now()

                        try:
                            updated_at = datetime.fromisoformat(updated_at_str)
                        except (ValueError, TypeError):
                            updated_at = created_at

                        # 计算相似度分数（BM25 返回负数，越小越好）
                        # 转换为 [0, 1] 范围的相似度分数
                        rank = dict(row).get("rank", 0)
                        score = max(0.0, min(1.0, 1.0 / (1.0 + abs(rank))))

                        # 构建值字典
                        value = {"content": content}
                        value.update(extra_meta)

                        items.append(
                            SearchItem(
                                namespace=namespace_prefix,
                                key=key,
                                value=value,
                                created_at=created_at,
                                updated_at=updated_at,
                                score=score,
                            )
                        )
                    except Exception as e:
                        logger.warning(f"构建 SearchItem 失败: {e}")
                        continue

            logger.debug(
                f"🔍 SQLiteFTSStore.asearch: namespace={namespace_prefix}, "
                f"query='{query[:30] if query else 'None'}...', results={len(items)}"
            )

        except Exception as e:
            logger.warning(f"SQLiteFTSStore.asearch failed: {e}")

        return items

    async def alist_namespaces(
        self,
        *,
        prefix: NamespacePath | None = None,
        suffix: NamespacePath | None = None,
        max_depth: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[tuple[str, ...]]:
        """
        异步列出命名空间

        Args:
            prefix: 命名空间前缀过滤
            suffix: 命名空间后缀过滤（暂不支持）
            max_depth: 最大深度（暂不支持）
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            命名空间列表
        """
        all_namespaces = list(self.PREDEFINED_NAMESPACES)

        # 应用前缀过滤
        if prefix:
            prefix_tuple = (
                tuple(prefix) if isinstance(prefix, (list, NamespacePath)) else prefix
            )
            all_namespaces = [
                ns
                for ns in all_namespaces
                if len(ns) >= len(prefix_tuple)
                and ns[: len(prefix_tuple)] == prefix_tuple
            ]

        # 应用后缀过滤
        if suffix:
            suffix_tuple = (
                tuple(suffix) if isinstance(suffix, (list, NamespacePath)) else suffix
            )
            all_namespaces = [
                ns
                for ns in all_namespaces
                if len(ns) >= len(suffix_tuple)
                and ns[-len(suffix_tuple) :] == suffix_tuple
            ]

        # 应用最大深度过滤
        if max_depth is not None and max_depth > 0:
            all_namespaces = [ns for ns in all_namespaces if len(ns) <= max_depth]

        # 应用偏移和限制
        return all_namespaces[offset : offset + limit]

    async def abatch(self, ops: Iterable[Op]) -> list[Result]:
        """
        异步批量操作

        Args:
            ops: 操作列表

        Returns:
            操作结果列表
        """
        results: list[Result] = []

        for op in ops:
            try:
                op_type = op.get("op")

                if op_type == "put":
                    await self.aput(
                        tuple(op["namespace"]),
                        op["key"],
                        op["value"],
                    )
                    results.append(None)

                elif op_type == "get":
                    result = await self.aget(
                        tuple(op["namespace"]),
                        op["key"],
                    )
                    results.append(result)

                elif op_type == "delete":
                    await self.adelete(
                        tuple(op["namespace"]),
                        op["key"],
                    )
                    results.append(None)

                elif op_type == "search":
                    result = await self.asearch(
                        tuple(op["namespace"]),
                        query=op.get("query"),
                        filter=op.get("filter"),
                        limit=op.get("limit", 10),
                    )
                    results.append(result)

                else:
                    logger.warning(f"未知的操作类型: {op_type}")
                    results.append(None)

            except Exception as e:
                logger.error(f"abatch operation failed: {op.get('op')}, error: {e}")
                results.append(None)

        return results

    # ==================== 同步方法（委托给异步实现）====================

    def put(
        self,
        namespace: tuple[str, ...],
        key: str,
        value: dict[str, Any],
        index: Literal[False] | list[str] | None = None,
        *,
        ttl: float | None | NotProvided = NOT_PROVIDED,
    ) -> None:
        """同步存储数据"""
        return _run_async(self.aput(namespace, key, value, index=index, ttl=ttl))

    def get(
        self,
        namespace: tuple[str, ...],
        key: str,
        *,
        refresh_ttl: bool | None = None,
    ) -> Optional[Item]:
        """同步获取数据"""
        return _run_async(self.aget(namespace, key, refresh_ttl=refresh_ttl))

    def delete(
        self,
        namespace: tuple[str, ...],
        key: str,
    ) -> None:
        """同步删除数据"""
        return _run_async(self.adelete(namespace, key))

    def search(
        self,
        namespace_prefix: tuple[str, ...],
        /,
        *,
        query: Optional[str] = None,
        filter: Optional[dict[str, Any]] = None,
        limit: int = 10,
        offset: int = 0,
        refresh_ttl: bool | None = None,
    ) -> list[SearchItem]:
        """同步关键词搜索"""
        return _run_async(
            self.asearch(
                namespace_prefix,
                query=query,
                filter=filter,
                limit=limit,
                offset=offset,
                refresh_ttl=refresh_ttl,
            )
        )

    def list_namespaces(
        self,
        *,
        prefix: NamespacePath | None = None,
        suffix: NamespacePath | None = None,
        max_depth: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[tuple[str, ...]]:
        """同步列出命名空间"""
        return _run_async(
            self.alist_namespaces(
                prefix=prefix,
                suffix=suffix,
                max_depth=max_depth,
                limit=limit,
                offset=offset,
            )
        )

    def batch(self, ops: Iterable[Op]) -> list[Result]:
        """同步批量操作"""
        return _run_async(self.abatch(ops))


# ==================== 全局单例 ====================

_fts_store_adapter: Optional[SQLiteFTSStore] = None


def get_langgraph_store() -> SQLiteFTSStore:
    """
    获取 LangGraph Store 适配器单例

    当 ENABLE_VECTOR_MEMORY=false 时使用 SQLite FTS5
    """
    global _fts_store_adapter
    if _fts_store_adapter is None:
        _fts_store_adapter = SQLiteFTSStore()
    return _fts_store_adapter


__all__ = [
    "SQLiteFTSStore",
    "get_langgraph_store",
]
