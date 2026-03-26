"""
ChromaDB 向量存储服务

使用 ChromaDB 替代手动实现的 SQLite + NumPy 向量存储
ChromaDB 是一个轻量级、易用的向量数据库，具有以下优势：
- 纯 Python 实现，无需额外服务
- 内置相似度搜索
- 支持元数据过滤
- 自动持久化
"""

import logging
from typing import List, Dict, Optional, Any
from pathlib import Path
from datetime import datetime

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

from app.core.llm_factory import LLMFactory
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ChromaVectorStore:
    """
    ChromaDB 向量存储服务

    支持：
    - 故障记忆向量存储
    - 知识库向量存储
    - 会话记忆向量存储
    - 语义相似度搜索
    """

    # 集合名称
    COLLECTION_INCIDENTS = "incident_memories"
    COLLECTION_KNOWLEDGE = "knowledge_memories"
    COLLECTION_SESSIONS = "session_memories"

    def __init__(self, persist_directory: str = "./data/chromadb"):
        """
        初始化 ChromaDB 向量存储

        Args:
            persist_directory: 持久化目录
        """
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        # 初始化 ChromaDB 客户端（持久化模式）
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(
                anonymized_telemetry=False,  # 禁用遥测
                allow_reset=True
            )
        )

        # 获取或创建集合
        self._init_collections()

        # 获取 embedding 函数
        self._embedding_function = None

        logger.info(f"✅ ChromaDB 向量存储初始化完成 | 目录: {persist_directory}")

    def _init_collections(self):
        """初始化或获取集合"""
        self.collection_incidents = self._get_or_create_collection(
            self.COLLECTION_INCIDENTS,
            {"description": "故障记忆存储 - 存储历史故障案例和解决方案", "type": "incidents"}
        )
        self.collection_knowledge = self._get_or_create_collection(
            self.COLLECTION_KNOWLEDGE,
            {"description": "知识库存储 - 存储运维知识和最佳实践", "type": "knowledge"}
        )
        self.collection_sessions = self._get_or_create_collection(
            self.COLLECTION_SESSIONS,
            {"description": "会话记忆存储 - 存储对话历史", "type": "sessions"}
        )

    def _get_or_create_collection(self, name: str, metadata: Dict[str, str] = None):
        """获取或创建集合"""
        try:
            # 尝试获取现有集合
            collection = self.client.get_collection(name=name)
            logger.debug(f"📦 获取现有集合: {name}")
            return collection
        except Exception:
            # 集合不存在，创建新集合
            collection = self.client.create_collection(
                name=name,
                metadata=metadata or {}
            )
            logger.info(f"📦 创建新集合: {name}")
            return collection

    @property
    def embedding_function(self):
        """延迟加载 embedding 函数，优先使用 Ollama 本地 embedding"""
        if self._embedding_function is None:
            settings = get_settings()
            ollama_base = settings.OLLAMA_BASE_URL.rstrip("/")

            # 优先：Ollama 本地 embedding（不依赖外部服务）
            try:
                import httpx
                resp = httpx.get(f"{ollama_base}/api/tags", timeout=2)
                models = [m["name"] for m in resp.json().get("models", [])]
                embed_model = next(
                    (m for m in models if any(k in m for k in ["nomic-embed", "bge-m3", "embed"])),
                    None,
                )
                if embed_model:
                    self._embedding_function = embedding_functions.OllamaEmbeddingFunction(
                        url=f"{ollama_base}/api/embeddings",
                        model_name=embed_model,
                    )
                    logger.info(f"🔑 ChromaDB 使用 Ollama Embedding: {embed_model}")
                    return self._embedding_function
            except Exception as e:
                logger.debug(f"Ollama embedding 不可用: {e}")

            # 降级：OpenAI embedding
            if settings.OPENAI_API_KEY:
                self._embedding_function = embedding_functions.OpenAIEmbeddingFunction(
                    api_key=settings.OPENAI_API_KEY,
                    model_name="text-embedding-3-small",
                    openai_api_base=settings.OPENAI_BASE_URL,
                )
                logger.info("🔑 ChromaDB 使用 OpenAI Embedding")
            else:
                # 最终降级：ChromaDB 默认 embedding（sentence-transformers，纯本地）
                self._embedding_function = embedding_functions.DefaultEmbeddingFunction()
                logger.info("🔑 ChromaDB 使用默认 Embedding (sentence-transformers)")

        return self._embedding_function

    async def store_incident(
        self,
        content: str,
        incident_type: str = "general",
        title: str = None,
        resolution: str = None,
        root_cause: str = None,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        存储故障记忆

        Args:
            content: 故障内容描述
            incident_type: 故障类型（kubernetes/database/network等）
            title: 故障标题
            resolution: 解决方案
            root_cause: 根本原因
            metadata: 额外元数据

        Returns:
            记忆 ID
        """
        doc_id = f"incident_{datetime.now().timestamp()}"
        metadatas = {
            "type": incident_type,
            "created_at": datetime.now().isoformat(),
            "title": title or "",
            "has_resolution": bool(resolution),
            "has_root_cause": bool(root_cause),
            **(metadata or {})
        }

        self.collection_incidents.add(
            documents=[content],
            metadatas=[metadatas],
            ids=[doc_id]
        )

        logger.debug(f"💾 存储故障记忆: {doc_id} | 类型: {incident_type}")
        return doc_id

    async def store_knowledge(
        self,
        title: str,
        content: str,
        category: str = "general",
        tags: List[str] = None,
        source: str = None,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        存储知识

        Args:
            title: 知识标题
            content: 知识内容
            category: 分类（kubernetes/database/network等）
            tags: 标签列表
            source: 来源
            metadata: 额外元数据

        Returns:
            记忆 ID
        """
        doc_id = f"knowledge_{datetime.now().timestamp()}"
        metadatas = {
            "category": category,
            "tags": ",".join(tags or []),
            "source": source or "",
            "created_at": datetime.now().isoformat(),
            **(metadata or {})
        }

        self.collection_knowledge.add(
            documents=[content],
            metadatas=[metadatas],
            ids=[doc_id]
        )

        logger.debug(f"💾 存储知识: {doc_id} | 分类: {category}")
        return doc_id

    async def store_session_message(
        self,
        session_id: str,
        role: str,
        content: str,
        importance: float = 0.5
    ) -> str:
        """
        存储会话消息

        Args:
            session_id: 会话 ID
            role: 角色（user/assistant/system）
            content: 消息内容
            importance: 重要性分数（0-1）

        Returns:
            记忆 ID
        """
        doc_id = f"session_{session_id}_{datetime.now().timestamp()}"
        metadatas = {
            "session_id": session_id,
            "role": role,
            "importance": importance,
            "created_at": datetime.now().isoformat()
        }

        self.collection_sessions.add(
            documents=[content],
            metadatas=[metadatas],
            ids=[doc_id]
        )

        logger.debug(f"💾 存储会话消息: {doc_id}")
        return doc_id

    async def search_similar_incidents(
        self,
        query: str,
        top_k: int = 5,
        incident_type: str = None,
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        搜索相似故障案例

        Args:
            query: 查询内容
            top_k: 返回结果数量
            incident_type: 过滤故障类型（可选）
            threshold: 相似度阈值（ChromaDB 使用距离，需转换）

        Returns:
            相似故障列表
        """
        # 构建查询条件
        where = {"type": incident_type} if incident_type else None

        results = self.collection_incidents.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"]
        )

        incidents = []
        if results and results['documents'] and len(results['documents']) > 0:
            for i, doc in enumerate(results['documents'][0]):
                distance = results['distances'][0][i]
                # ChromaDB 使用 L2 距离，转换为相似度 (0-1)
                # L2 距离越小，相似度越高
                similarity = max(0, 1 - distance)

                if similarity >= threshold:
                    metadata = results['metadatas'][0][i] or {}
                    incidents.append({
                        "id": f"incident_{i}",
                        "content": doc,
                        "title": metadata.get("title", ""),
                        "incident_type": metadata.get("type", ""),
                        "resolution": metadata.get("resolution", ""),
                        "root_cause": metadata.get("root_cause", ""),
                        "similarity": similarity,
                        "created_at": metadata.get("created_at", "")
                    })

        logger.debug(f"🔍 搜索相似故障: query='{query[:50]}...', 结果数={len(incidents)}")
        return incidents

    async def search_knowledge(
        self,
        query: str,
        top_k: int = 5,
        category: str = None,
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        搜索知识库

        Args:
            query: 查询内容
            top_k: 返回结果数量
            category: 过滤分类（可选）
            threshold: 相似度阈值

        Returns:
            相关知识列表
        """
        where = {"category": category} if category else None

        results = self.collection_knowledge.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"]
        )

        knowledge = []
        if results and results['documents'] and len(results['documents']) > 0:
            for i, doc in enumerate(results['documents'][0]):
                distance = results['distances'][0][i]
                similarity = max(0, 1 - distance)

                if similarity >= threshold:
                    metadata = results['metadatas'][0][i] or {}
                    knowledge.append({
                        "id": f"knowledge_{i}",
                        "title": metadata.get("title", doc[:50]),
                        "content": doc,
                        "category": metadata.get("category", ""),
                        "tags": metadata.get("tags", "").split(",") if metadata.get("tags") else [],
                        "source": metadata.get("source", ""),
                        "similarity": similarity,
                        "created_at": metadata.get("created_at", "")
                    })

        logger.debug(f"🔍 搜索知识: query='{query[:50]}...', 结果数={len(knowledge)}")
        return knowledge

    async def search_session_history(
        self,
        session_id: str,
        query: str = None,
        top_k: int = 10,
        importance_threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        搜索会话历史

        Args:
            session_id: 会话 ID
            query: 语义搜索查询（可选）
            top_k: 返回结果数量
            importance_threshold: 重要性阈值

        Returns:
            会话消息列表
        """
        if query:
            # 语义搜索
            results = self.collection_sessions.query(
                query_texts=[query],
                n_results=top_k,
                where={"session_id": session_id},
                include=["documents", "metadatas", "distances"]
            )

            messages = []
            if results and results['documents'] and len(results['documents']) > 0:
                for i, doc in enumerate(results['documents'][0]):
                    metadata = results['metadatas'][0][i] or {}
                    importance = float(metadata.get("importance", 0.5))
                    if importance >= importance_threshold:
                        messages.append({
                            "role": metadata.get("role", "unknown"),
                            "content": doc,
                            "importance": importance,
                            "created_at": metadata.get("created_at", "")
                        })
            return messages
        else:
            # 获取最近的会话消息
            results = self.collection_sessions.get(
                where={"session_id": session_id},
                limit=top_k,
                include=["documents", "metadatas"]
            )

            messages = []
            if results and results['documents'] and len(results['documents']) > 0:
                for i, doc in enumerate(results['documents']):
                    metadata = results['metadatas'][i] or {}
                    importance = float(metadata.get("importance", 0.5))
                    if importance >= importance_threshold:
                        messages.append({
                            "role": metadata.get("role", "unknown"),
                            "content": doc,
                            "importance": importance,
                            "created_at": metadata.get("created_at", "")
                        })
            return messages

    async def search_similar(
        self,
        query: str,
        table: str = "incident_memories",
        top_k: int = 5,
        threshold: float = 0.7,
        filters: dict = None
    ) -> List[Dict[str, Any]]:
        """
        通用相似度搜索（兼容旧接口）

        Args:
            query: 查询文本（ChromaDB 会自动生成 embedding）
            table: 表名/集合名
            top_k: 返回结果数量
            threshold: 相似度阈值
            filters: 元数据过滤条件

        Returns:
            相似结果列表
        """
        # 根据 table 路由到对应的集合
        if table == "incident_memories" or table == self.COLLECTION_INCIDENTS:
            # 提取 incident_type 过滤器
            incident_type = filters.get("incident_type") if filters else None
            results = await self.search_similar_incidents(
                query=query,
                top_k=top_k,
                incident_type=incident_type,
                threshold=threshold
            )
            return results

        elif table == "knowledge_memories" or table == self.COLLECTION_KNOWLEDGE:
            # 提取 category 过滤器
            category = filters.get("category") if filters else None
            results = await self.search_knowledge(
                query=query,
                top_k=top_k,
                category=category,
                threshold=threshold
            )
            return results

        elif table == "session_memories" or table == self.COLLECTION_SESSIONS:
            # 提取 session_id 过滤器
            session_id = filters.get("session_id") if filters else None
            results = await self.search_session_history(
                query=query,
                session_id=session_id,
                top_k=top_k,
                importance_threshold=threshold
            )
            return results

        else:
            logger.warning(f"❌ 未知的表名: {table}")
            return []

    async def get_memory_stats(self) -> Dict[str, int]:
        """获取记忆统计信息"""
        return {
            "incident_memories": self.collection_incidents.count(),
            "knowledge_memories": self.collection_knowledge.count(),
            "session_memories": self.collection_sessions.count(),
        }

    async def delete_incident(self, incident_id: str) -> bool:
        """删除故障记忆"""
        try:
            self.collection_incidents.delete(ids=[incident_id])
            logger.debug(f"🗑️ 删除故障记忆: {incident_id}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ 删除故障记忆失败: {e}")
            return False

    async def delete_knowledge(self, knowledge_id: str) -> bool:
        """删除知识"""
        try:
            self.collection_knowledge.delete(ids=[knowledge_id])
            logger.debug(f"🗑️ 删除知识: {knowledge_id}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ 删除知识失败: {e}")
            return False

    async def clear_session(self, session_id: str) -> bool:
        """清除会话记忆"""
        try:
            # 获取会话的所有消息 ID
            results = self.collection_sessions.get(
                where={"session_id": session_id},
                include=["ids"]
            )

            if results and results['ids']:
                self.collection_sessions.delete(ids=results['ids'])
                logger.debug(f"🗑️ 清除会话记忆: {session_id}, 消息数={len(results['ids'])}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ 清除会话记忆失败: {e}")
            return False


# 全局单例
_chroma_store: Optional[ChromaVectorStore] = None


def get_chroma_store() -> ChromaVectorStore:
    """获取 ChromaDB 向量存储单例"""
    global _chroma_store
    if _chroma_store is None:
        _chroma_store = ChromaVectorStore()
    return _chroma_store


__all__ = [
    "ChromaVectorStore",
    "get_chroma_store",
]
