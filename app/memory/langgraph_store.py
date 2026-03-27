"""
ChromaDB 适配器 - 实现 LangGraph BaseStore 接口

将 ChromaDB 包装为 LangGraph 的 BaseStore，支持：
- 长期记忆存储
- 语义相似度搜索
- 会话隔离

参考：https://langchain-ai.github.io/langgraph/reference/store/#langgraph.store.base.BaseStore
"""

from __future__ import annotations

import asyncio
import logging
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

if TYPE_CHECKING:
    pass

from app.memory.chroma_store import get_chroma_store

logger = logging.getLogger(__name__)


# 线程池执行器（用于同步方法调用异步实现）
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="chromadb_store_")


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


class ChromaDBStore(BaseStore):
    """
    ChromaDB 适配器 - 实现 LangGraph BaseStore 接口

    命名空间映射：
    - ("memories", "incidents") -> incident_memories 集合
    - ("memories", "knowledge") -> knowledge_memories 集合
    - ("memories", "sessions") -> session_memories 集合

    支持的操作：
    - put/aput: 存储数据（支持 TTL 参数但暂不生效）
    - get/aget: 获取数据
    - delete/adelete: 删除数据
    - search/asearch: 语义搜索
    - list_namespaces/alist_namespaces: 列出命名空间
    - batch/abatch: 批量操作

    注意：
    - TTL 功能暂不支持，数据会永久存储直到手动删除
    - refresh_ttl 参数暂不支持
    """

    # 预定义的命名空间
    PREDEFINED_NAMESPACES = [
        ("memories", "incidents"),
        ("memories", "knowledge"),
        ("memories", "sessions"),
    ]

    def __init__(self):
        """初始化 ChromaDB 存储适配器"""
        self.chroma = get_chroma_store()
        logger.info("✅ ChromaDBStore 适配器初始化完成")

    # ==================== 内部辅助方法 ====================

    def _namespace_to_collection(self, namespace: tuple[str, ...]) -> str:
        """
        将命名空间映射到 ChromaDB 集合名

        Args:
            namespace: 命名空间元组

        Returns:
            集合名称
        """
        if not namespace:
            return "knowledge_memories"

        if namespace[0] == "memories" and len(namespace) >= 2:
            if namespace[1] == "incidents":
                return "incident_memories"
            elif namespace[1] == "knowledge":
                return "knowledge_memories"
            elif namespace[1] == "sessions":
                return "session_memories"

        return "knowledge_memories"

    def _get_collection(self, namespace: tuple[str, ...]):
        """
        获取对应的 ChromaDB 集合

        Args:
            namespace: 命名空间元组

        Returns:
            ChromaDB 集合对象
        """
        collection_name = self._namespace_to_collection(namespace)

        collection_map = {
            "incident_memories": self.chroma.collection_incidents,
            "knowledge_memories": self.chroma.collection_knowledge,
            "session_memories": self.chroma.collection_sessions,
        }

        return collection_map.get(collection_name, self.chroma.collection_knowledge)

    def _build_metadata(
        self, value: dict[str, Any], namespace: tuple[str, ...]
    ) -> dict[str, Any]:
        """
        构建存储元数据

        Args:
            value: 数据值
            namespace: 命名空间

        Returns:
            元数据字典
        """
        now = datetime.now()
        metadata = {
            "namespace": "/".join(namespace) if namespace else "",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        # 添加额外的元数据（排除 content 和复杂类型）
        for k, v in value.items():
            if k == "content":
                continue
            if isinstance(v, (dict, list)):
                continue
            metadata[k] = str(v) if not isinstance(v, str) else v

        return metadata

    def _build_item(
        self,
        doc: str,
        metadata: dict[str, Any],
        key: str,
        namespace: tuple[str, ...],
    ) -> Item:
        """
        从文档和元数据构建 Item 对象

        Args:
            doc: 文档内容
            metadata: 元数据
            key: 键
            namespace: 命名空间

        Returns:
            Item 对象
        """
        created_at_str = metadata.get("created_at", datetime.now().isoformat())
        updated_at_str = metadata.get("updated_at", created_at_str)

        try:
            created_at = datetime.fromisoformat(created_at_str)
        except (ValueError, TypeError):
            created_at = datetime.now()

        try:
            updated_at = datetime.fromisoformat(updated_at_str)
        except (ValueError, TypeError):
            updated_at = created_at

        return Item(
            value={"content": doc, **metadata},
            key=key,
            namespace=namespace,
            created_at=created_at,
            updated_at=updated_at,
        )

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

        Note:
            当前实现不支持 TTL 和 index，数据会永久存储直到手动删除
        """
        collection = self._get_collection(namespace)
        metadata = self._build_metadata(value, namespace)
        content = value.get("content", str(value))

        # 如果有 TTL，记录警告（当前不支持）
        if ttl is not NOT_PROVIDED and ttl is not None:
            logger.warning(f"TTL 参数暂不支持，将忽略 ttl={ttl}")

        # index 参数暂不支持
        if index is not None and index is not False:
            logger.debug(f"index 参数暂不支持，将忽略 index={index}")

        collection.upsert(
            documents=[content],
            metadatas=[metadata],
            ids=[key],
        )

        logger.debug(f"💾 ChromaDBStore.aput: key={key}, namespace={namespace}")

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
        collection = self._get_collection(namespace)

        try:
            results = collection.get(
                ids=[key],
                include=["documents", "metadatas"],
            )

            if results and results.get("documents") and len(results["documents"]) > 0:
                doc = results["documents"][0]
                metadata = (
                    results["metadatas"][0]
                    if results.get("metadatas") and len(results["metadatas"]) > 0
                    else {}
                )

                return self._build_item(doc, metadata, key, namespace)

        except Exception as e:
            logger.debug(f"ChromaDBStore.aget: key={key} not found: {e}")

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
        collection = self._get_collection(namespace)

        try:
            collection.delete(ids=[key])
            logger.debug(f"🗑️ ChromaDBStore.adelete: key={key}")
        except Exception as e:
            logger.warning(f"ChromaDBStore.adelete failed: {e}")

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
        异步语义搜索

        Args:
            namespace_prefix: 命名空间前缀（位置参数）
            query: 搜索查询（语义搜索）
            filter: 过滤条件
            limit: 返回数量限制
            offset: 偏移量（暂不支持，需要手动处理）
            refresh_ttl: 是否刷新 TTL（暂不支持）

        Returns:
            SearchItem 列表
        """
        collection = self._get_collection(namespace_prefix)

        # ChromaDB 不支持 offset，需要手动处理
        actual_limit = limit + offset if offset > 0 else limit

        try:
            if query:
                # 语义搜索
                results = collection.query(
                    query_texts=[query],
                    n_results=actual_limit,
                    where=filter,
                    include=["documents", "metadatas", "distances"],
                )
            else:
                # 获取所有匹配的数据
                results = collection.get(
                    where=filter,
                    limit=actual_limit,
                    include=["documents", "metadatas"],
                )
                # 转换为 query 格式以便统一处理
                if results and results.get("documents"):
                    doc_count = len(results["documents"])
                    results = {
                        "ids": [results.get("ids", list(range(doc_count)))],
                        "documents": [results["documents"]],
                        "metadatas": [results.get("metadatas", [{}] * doc_count)],
                        "distances": [[0.0] * doc_count],
                    }

            items = []

            if results and results.get("documents") and len(results["documents"]) > 0:
                docs = results["documents"][0]
                metas = (
                    results.get("metadatas", [[]])[0]
                    if results.get("metadatas")
                    else []
                )
                ids = (
                    results.get("ids", [[]])[0]
                    if results.get("ids")
                    else list(range(len(docs)))
                )
                distances = (
                    results.get("distances", [[]])[0]
                    if results.get("distances")
                    else [0.0] * len(docs)
                )

                # 应用 offset
                start_idx = offset if offset > 0 else 0

                for i in range(start_idx, len(docs)):
                    if len(items) >= limit:
                        break

                    doc = docs[i]
                    metadata = metas[i] if i < len(metas) else {}
                    doc_id = str(ids[i]) if i < len(ids) else str(i)
                    distance = distances[i] if i < len(distances) else 0.0

                    # 转换距离为相似度分数（距离越小，分数越高）
                    # ChromaDB 默认使用 L2 距离，范围通常是 [0, +inf)
                    # 我们将其转换为 [0, 1] 范围的相似度分数
                    score = max(0.0, min(1.0, 1.0 / (1.0 + distance)))

                    created_at_str = metadata.get(
                        "created_at", datetime.now().isoformat()
                    )
                    updated_at_str = metadata.get("updated_at", created_at_str)

                    try:
                        created_at = datetime.fromisoformat(created_at_str)
                    except (ValueError, TypeError):
                        created_at = datetime.now()

                    try:
                        updated_at = datetime.fromisoformat(updated_at_str)
                    except (ValueError, TypeError):
                        updated_at = created_at

                    items.append(
                        SearchItem(
                            namespace=namespace_prefix,
                            key=doc_id,
                            value={"content": doc, **metadata},
                            created_at=created_at,
                            updated_at=updated_at,
                            score=score,
                        )
                    )

            logger.debug(
                f"🔍 ChromaDBStore.asearch: namespace={namespace_prefix}, "
                f"query='{query[:30] if query else 'None'}...', results={len(items)}"
            )

            return items

        except Exception as e:
            logger.warning(f"ChromaDBStore.asearch failed: {e}")
            return []

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
        """同步语义搜索"""
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

_chroma_store_adapter: Optional[ChromaDBStore] = None


def get_langgraph_store() -> ChromaDBStore:
    """获取 LangGraph Store 适配器单例"""
    global _chroma_store_adapter
    if _chroma_store_adapter is None:
        _chroma_store_adapter = ChromaDBStore()
    return _chroma_store_adapter


__all__ = [
    "ChromaDBStore",
    "get_langgraph_store",
]
