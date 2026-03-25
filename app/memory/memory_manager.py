"""
记忆管理模块 - 统一管理向量记忆

功能：
- 故障记忆管理（运维领域）
- 知识库管理（运维知识）
- 会话记忆管理（通过 Mem0 处理通用对话记忆）
- 智能上下文构建（混合两层记忆）

架构：
- Mem0 (通用对话记忆): 用户偏好、会话上下文
- MemoryManager (运维领域记忆): 故障、知识库

支持两种向量存储后端：
- ChromaDB (推荐): 使用 ChromaDB 向量数据库
- SQLite + NumPy (兼容): 手动实现的向量存储（向后兼容）
"""

import asyncio
import logging
import os
from typing import List, Dict, Optional, Any
from datetime import datetime
from collections import deque

from app.core.llm_factory import LLMFactory
from app.core.config import get_settings
from app.core.constants import is_incident_handling, MiddlewareConfig
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 尝试导入 Mem0 适配器
try:
    from app.memory.mem0_adapter import get_mem0_adapter, MEM0_AVAILABLE
    HAS_MEM0 = MEM0_AVAILABLE
except ImportError:
    HAS_MEM0 = False
    logger.warning("⚠️ Mem0 适配器不可用")

# 根据环境变量选择向量存储后端
USE_CHROMADB = os.getenv("USE_CHROMADB", "true").lower() == "true"

if USE_CHROMADB:
    try:
        from app.memory.chroma_store import get_chroma_store
        VECTOR_STORE_CLASS = "chromadb"
        logger.info("✅ 使用 ChromaDB 向量存储")
    except ImportError:
        USE_CHROMADB = False
        logger.warning("⚠️ ChromaDB 不可用，回退到 SQLite 向量存储")
        from app.memory.vector_store import get_vector_store
        VECTOR_STORE_CLASS = "sqlite"
else:
    from app.memory.vector_store import get_vector_store
    VECTOR_STORE_CLASS = "sqlite"
    logger.info("✅ 使用 SQLite 向量存储")


class MemoryManager:
    """
    记忆管理器 - 统一管理短期/长期记忆

    混合架构：
    - Mem0: 通用对话记忆（用户偏好、会话上下文）
    - 向量存储: 运维领域记忆（故障、知识库）
    """

    def __init__(self, db_path: str = "./data/ops_agent_v2.db", user_id: str = None):
        # 根据配置选择向量存储
        if USE_CHROMADB:
            self.vector_store = get_chroma_store()
        else:
            self.vector_store = get_vector_store()

        self._embedding_model = None
        self._llm = None
        self._store_type = "chromadb" if USE_CHROMADB else "sqlite"

        # 初始化 Mem0（通用对话记忆）
        self._mem0_adapter = None
        self._mem0_user_id = user_id or "default_user"
        self._mem0_enabled = False

        settings = get_settings()
        if HAS_MEM0 and settings.MEM0_ENABLED:
            try:
                self._mem0_adapter = get_mem0_adapter(
                    user_id=self._mem0_user_id,
                    api_key=settings.MEM0_API_KEY,
                    provider=settings.MEM0_PROVIDER,
                    model=settings.MEM0_MODEL
                )
                self._mem0_enabled = self._mem0_adapter.enabled
                if self._mem0_enabled:
                    logger.info(f"✅ Mem0 已启用 | user_id={self._mem0_user_id}")
            except Exception as e:
                logger.warning(f"⚠️ Mem0 初始化失败: {e}")

        logger.info(
            f"🧠 记忆管理器初始化完成 | "
            f"向量存储: {self._store_type} | "
            f"Mem0: {'✅' if self._mem0_enabled else '❌'}"
        )

    @property
    def embedding_model(self):
        """延迟加载 embedding 模型"""
        if self._embedding_model is None:
            self._embedding_model = LLMFactory.create_embeddings()
        return self._embedding_model

    @property
    def llm(self):
        """延迟加载 LLM"""
        if self._llm is None:
            self._llm = LLMFactory.create_llm()
        return self._llm

    async def get_embedding(self, text: str) -> List[float]:
        """获取文本向量"""
        try:
            embedding = await self.embedding_model.aembed_query(text)
            return embedding
        except Exception as e:
            logger.warning(f"获取向量失败: {e}，返回零向量")
            # 返回零向量作为后备
            return [0.0] * 1536  # OpenAI embedding 默认维度

    # ==================== 故障记忆 ====================

    async def remember_incident(
        self,
        content: str,
        incident_type: str = "alert",
        title: str = None,
        resolution: str = None,
        root_cause: str = None,
        metadata: dict = None,
        incident_id: str = None
    ) -> int:
        """记住一个故障事件"""
        # ChromaDB 自动处理 embeddings，SQLite 需要手动生成
        if self._store_type == "chromadb":
            memory_id = await self.vector_store.store_incident(
                content=content,
                incident_type=incident_type,
                title=title,
                resolution=resolution,
                root_cause=root_cause,
                metadata=metadata
            )
        else:
            embedding = await self.get_embedding(content)
            memory_id = await self.vector_store.store_incident(
                content=content,
                embedding=embedding,
                incident_type=incident_type,
                title=title,
                resolution=resolution,
                root_cause=root_cause,
                metadata=metadata,
                incident_id=incident_id
            )
        logger.info(f"📝 记住故障事件: {title or incident_type} (ID: {memory_id})")
        return memory_id

    async def recall_similar_incidents(
        self,
        query: str,
        incident_type: str = None,
        top_k: int = 5,
        threshold: float = 0.7
    ) -> List[Dict]:
        """回忆相似的故障"""
        filters = {"incident_type": incident_type} if incident_type else None

        # ChromaDB 使用查询文本，SQLite 使用 embedding
        if self._store_type == "chromadb":
            results = await self.vector_store.search_similar(
                query=query,
                table="incident_memories",
                top_k=top_k,
                threshold=threshold,
                filters=filters
            )
        else:
            embedding = await self.get_embedding(query)
            results = await self.vector_store.search_similar(
                query_embedding=embedding,
                table="incident_memories",
                top_k=top_k,
                threshold=threshold,
                filters=filters
            )

        # 更新访问记录（仅 SQLite）
        if self._store_type != "chromadb":
            for result in results:
                await self.vector_store.update_access(result["id"], "incident_memories")

        logger.info(f"🔍 回忆相似故障: {len(results)} 个")
        return results

    async def get_recent_incidents(
        self,
        days: int = 7,
        limit: int = 50,
        incident_type: str = None
    ) -> List[Dict]:
        """获取最近的故障"""
        return await self.vector_store.get_recent_incidents(
            days=days,
            limit=limit,
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
    ) -> int:
        """学习知识"""
        # ChromaDB 自动处理 embeddings，SQLite 需要手动生成
        if self._store_type == "chromadb":
            memory_id = await self.vector_store.store_knowledge(
                title=title,
                content=content,
                category=category,
                tags=tags,
                source=source,
                metadata=metadata
            )
        else:
            embedding = await self.get_embedding(content)
            memory_id = await self.vector_store.store_knowledge(
                title=title,
                content=content,
                embedding=embedding,
                category=category,
                tags=tags,
                source=source,
                metadata=metadata
            )
        logger.info(f"📚 学习知识: {title} (ID: {memory_id})")
        return memory_id

    async def query_knowledge(
        self,
        query: str,
        category: str = None,
        top_k: int = 5,
        threshold: float = 0.7
    ) -> List[Dict]:
        """查询知识库"""
        filters = {"category": category} if category else None

        # ChromaDB 使用查询文本，SQLite 使用 embedding
        if self._store_type == "chromadb":
            results = await self.vector_store.search_similar(
                query=query,
                table="knowledge_memories",
                top_k=top_k,
                threshold=threshold,
                filters=filters
            )
        else:
            embedding = await self.get_embedding(query)
            results = await self.vector_store.search_similar(
                query_embedding=embedding,
                table="knowledge_memories",
                top_k=top_k,
                threshold=threshold,
                filters=filters
            )

        logger.info(f"📖 查询知识库: {len(results)} 个结果")
        return results

    # ==================== 会话记忆 ====================

    async def remember_message(
        self,
        session_id: str,
        role: str,
        content: str,
        importance: float = 0.5
    ) -> int:
        """记住会话消息"""
        # ChromaDB 自动处理 embeddings，SQLite 需要手动生成
        if self._store_type == "chromadb":
            return await self.vector_store.store_session_message(
                session_id=session_id,
                role=role,
                content=content,
                importance=importance
            )
        else:
            embedding = await self.get_embedding(content)
            return await self.vector_store.store_session_message(
                session_id=session_id,
                role=role,
                content=content,
                embedding=embedding,
                importance=importance
            )

    async def recall_session_context(
        self,
        session_id: str,
        query: str,
        top_k: int = 10
    ) -> List[Dict]:
        """回忆会话上下文"""
        # ChromaDB 使用查询文本，SQLite 使用 embedding
        if self._store_type == "chromadb":
            return await self.vector_store.search_similar(
                query=query,
                table="session_memories",
                top_k=top_k,
                threshold=0.5,  # 较低阈值，获取更多上下文
                filters={"session_id": session_id}
            )
        else:
            embedding = await self.get_embedding(query)
            return await self.vector_store.search_similar(
                query_embedding=embedding,
                table="session_memories",
                top_k=top_k,
                threshold=0.5,  # 较低阈值，获取更多上下文
                filters={"session_id": session_id}
            )

    # ==================== 智能上下文构建 ====================

    def _classify_intent(self, query: str) -> str:
        """
        分类查询意图（参考 OpenClaw）
        
        Returns:
            - "specific_resource": 具体资源查询（版本、配置、状态等）
            - "incident_diagnosis": 故障诊断（错误、异常、失败等）
            - "cluster_overview": 集群概况（列表、总览、统计等）
            - "general": 通用查询
        """
        query_lower = query.lower()
        
        # 1. 具体资源查询
        if any(kw in query_lower for kw in ["版本", "配置", "状态", "日志", "yaml", "版本号"]):
            return "specific_resource"
        
        # 2. 故障诊断
        if any(kw in query_lower for kw in ["错误", "异常", "失败", "告警", "故障", "诊断", "排查"]):
            return "incident_diagnosis"
        
        # 3. 集群概况
        if any(kw in query_lower for kw in ["概况", "总览", "多少", "列表", "概览", "统计", "总共有"]):
            return "cluster_overview"
        
        # 4. 通用查询
        return "general"

    async def smart_search(
        self,
        query: str,
        context: Dict[str, Any] = None,
        session_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        智能检索（参考 OpenClaw）
        
        ⚠️ 核心改进：
        1. 自动分类查询意图
        2. 根据意图选择检索策略
        3. 自动过滤记忆
        
        Args:
            query: 查询文本
            context: 上下文信息（包含 namespace, resource_type 等）
            session_id: 会话 ID
        
        Returns:
            记忆列表（已根据意图过滤）
        """
        context = context or {}
        
        # 1. 分类查询意图
        intent = self._classify_intent(query)
        logger.info(f"🎯 [Intent] 查询意图: {intent}")
        
        # 2. 根据意图选择检索策略
        if intent == "specific_resource":
            # 具体资源查询 → 不检索历史记忆（避免干扰）
            logger.info(f"🚫 [Memory] 具体资源查询，跳过历史记忆检索")
            return []
        
        elif intent == "incident_diagnosis":
            # 故障诊断 → 检索故障记忆和知识库
            logger.info(f"🔍 [Memory] 故障诊断，检索故障记忆和知识库")
            return await self.memory_search(
                query=query,
                max_results=5,
                min_score=0.7,
                include_mem0=True,
                include_incidents=True,
                include_knowledge=True,
                include_session=True,
                session_id=session_id
            )
        
        elif intent == "cluster_overview":
            # 集群概况 → 检索知识库（低相关性阈值）
            logger.info(f"📊 [Memory] 集群概况，检索知识库")
            return await self.memory_search(
                query=query,
                max_results=10,
                min_score=0.6,  # 较低阈值
                include_mem0=False,
                include_incidents=False,
                include_knowledge=True,
                include_session=False
            )
        
        else:
            # 通用查询 → 默认策略
            logger.info(f"🔍 [Memory] 通用查询，使用默认策略")
            return await self.memory_search(
                query=query,
                max_results=5,
                min_score=0.7,
                include_mem0=True,
                include_incidents=True,
                include_knowledge=True,
                include_session=False
            )

    # ==================== 检索式访问（参考 OpenClaw）====================

    async def memory_search(
        self,
        query: str,
        max_results: int = 5,
        min_score: float = 0.7,
        include_mem0: bool = True,
        include_incidents: bool = True,
        include_knowledge: bool = True,
        include_session: bool = False,
        session_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        语义搜索记忆（参考 OpenClaw 的检索式访问）
        
        ⚠️ 关键区别：
        - 不自动注入到上下文
        - 返回记忆列表，由调用者决定如何使用
        - 参考 OpenClaw 的 memory_search 工具设计
        
        Args:
            query: 查询文本
            max_results: 最大返回数量
            min_score: 最小相似度阈值（0-1）
            include_mem0: 是否包含 Mem0 通用对话记忆
            include_incidents: 是否包含故障记忆
            include_knowledge: 是否包含知识库
            include_session: 是否包含会话记忆
            session_id: 会话 ID（用于会话记忆检索）
        
        Returns:
            记忆列表，每个记忆包含：
            - content: 记忆内容
            - source: 来源（mem0/incident/knowledge/session）
            - similarity: 相似度（0-1）
            - metadata: 元数据
        """
        results = []
        
        # 1. 从 Mem0 检索通用对话记忆
        if include_mem0 and self._mem0_enabled:
            try:
                mem0_results = await self._mem0_adapter.search_user_memory(
                    query=query,
                    limit=max_results
                )
                
                for r in mem0_results:
                    results.append({
                        "content": r.get("memory", ""),
                        "source": "mem0_user",
                        "similarity": 0.8,  # Mem0 不返回相似度，给默认值
                        "metadata": r.get("metadata", {})
                    })
                
                # 如果有 session_id，也检索会话记忆
                if session_id:
                    session_results = await self._mem0_adapter.search_session_memory(
                        session_id=session_id,
                        query=query,
                        limit=max_results
                    )
                    
                    for r in session_results:
                        results.append({
                            "content": r.get("memory", ""),
                            "source": "mem0_session",
                            "similarity": 0.8,
                            "metadata": r.get("metadata", {})
                        })
                
                logger.info(f"🔍 Mem0: 检索到 {len(mem0_results)} 条用户记忆")
                
            except Exception as e:
                logger.warning(f"⚠️ Mem0 检索失败: {e}")
        
        # 2. 从 ChromaDB 检索故障记忆
        if include_incidents:
            try:
                incidents = await self.recall_similar_incidents(
                    query=query,
                    top_k=max_results
                )
                
                for inc in incidents:
                    similarity = inc.get("similarity", 0)
                    
                    # 过滤低相关性的
                    if similarity >= min_score:
                        results.append({
                            "content": inc.get("content", ""),
                            "source": "incident",
                            "similarity": similarity,
                            "metadata": {
                                "title": inc.get("title"),
                                "incident_type": inc.get("incident_type"),
                                "resolution": inc.get("resolution"),
                                "root_cause": inc.get("root_cause")
                            }
                        })
                
                logger.info(f"🔍 故障记忆: 检索到 {len(incidents)} 条")
                
            except Exception as e:
                logger.warning(f"⚠️ 故障记忆检索失败: {e}")
        
        # 3. 从 ChromaDB 检索知识库
        if include_knowledge:
            try:
                knowledge = await self.query_knowledge(
                    query=query,
                    top_k=max_results
                )
                
                for k in knowledge:
                    similarity = k.get("similarity", 0)
                    
                    if similarity >= min_score:
                        results.append({
                            "content": k.get("content", ""),
                            "source": "knowledge",
                            "similarity": similarity,
                            "metadata": {
                                "title": k.get("title"),
                                "category": k.get("category"),
                                "tags": k.get("tags"),
                                "source": k.get("source")
                            }
                        })
                
                logger.info(f"🔍 知识库: 检索到 {len(knowledge)} 条")
                
            except Exception as e:
                logger.warning(f"⚠️ 知识库检索失败: {e}")
        
        # 4. 从 ChromaDB 检索会话记忆
        if include_session and session_id:
            try:
                session_contexts = await self.recall_session_context(
                    session_id=session_id,
                    query=query,
                    top_k=max_results
                )
                
                for ctx in session_contexts:
                    similarity = ctx.get("similarity", 0)
                    
                    if similarity >= min_score:
                        results.append({
                            "content": ctx.get("content", ""),
                            "source": "session",
                            "similarity": similarity,
                            "metadata": {
                                "role": ctx.get("role"),
                                "timestamp": ctx.get("timestamp")
                            }
                        })
                
                logger.info(f"🔍 会话记忆: 检索到 {len(session_contexts)} 条")
                
            except Exception as e:
                logger.warning(f"⚠️ 会话记忆检索失败: {e}")
        
        # 5. 按相似度排序并返回 Top-K
        sorted_results = sorted(
            results,
            key=lambda x: x.get("similarity", 0),
            reverse=True
        )
        
        return sorted_results[:max_results]

    async def build_context(
        self,
        user_query: str,
        session_id: str = None,
        include_incidents: bool = True,
        include_knowledge: bool = True,
        include_session: bool = False,
        include_mem0: bool = True,
        max_tokens: int = 3000,
        enable_truncation: bool = True
    ) -> str:
        """
        构建智能上下文（混合两层记忆，参考 OpenClaw）

        记忆层级：
        1. Mem0 通用对话记忆（用户偏好、会话上下文）
        2. 运维领域记忆（故障、知识库）
        
        ⚠️ Token 管理（参考 OpenClaw）：
        - 实时监控 token 使用量
        - 超过限制时自动截断
        - 优先保留高相关性记忆

        Args:
            user_query: 用户查询
            session_id: 会话 ID
            include_incidents: 是否包含故障记忆
            include_knowledge: 是否包含知识库
            include_session: 是否包含会话记忆（向量存储）
            include_mem0: 是否包含 Mem0 记忆
            max_tokens: 最大 token 数
            enable_truncation: 是否启用自动截断

        Returns:
            格式化的上下文字符串
        """
        context_parts = []
        current_tokens = 0
        original_max = max_tokens
        
        logger.info(f"📊 [Token] 开始构建上下文 | 预算: {max_tokens} tokens")

        # ===== 第一层：Mem0 通用对话记忆 =====
        if include_mem0 and self._mem0_enabled:
            try:
                mem0_context = await self._mem0_adapter.get_context_for_query(
                    query=user_query,
                    session_id=session_id,
                    include_user=True,
                    include_session=True,
                    max_tokens=max_tokens // 3  # 分配 1/3 token
                )
                if mem0_context:
                    # Token 检查（参考 OpenClaw）
                    mem0_tokens = self._estimate_tokens(mem0_context)
                    
                    if current_tokens + mem0_tokens > original_max:
                        logger.warning(f"⚠️ [Token] Mem0 上下文超出限制 | 当前: {current_tokens} + {mem0_tokens} > {original_max}")
                        # 截断
                        if enable_truncation:
                            mem0_context = self._truncate_to_token_limit(mem0_context, original_max - current_tokens)
                            mem0_tokens = self._estimate_tokens(mem0_context)
                        else:
                            mem0_context = ""
                            mem0_tokens = 0
                    
                    if mem0_context:
                        context_parts.append(f"## 🗣️ 对话记忆\n{mem0_context}")
                        current_tokens += mem0_tokens
                        max_tokens = original_max - current_tokens
                        logger.info(f"✅ [Token] Mem0 上下文已添加 | 使用: {mem0_tokens} tokens | 剩余: {max_tokens} tokens")
            except Exception as e:
                logger.warning(f"⚠️ Mem0 上下文获取失败: {e}")

        # ===== 第二层：运维领域记忆 =====

        # 1. 检索相关故障记忆
        if include_incidents:
            incidents = await self.recall_similar_incidents(user_query, top_k=3)
            if incidents:
                incident_context = self._format_incidents(incidents)
                if current_tokens + len(incident_context) < original_max:
                    context_parts.append(incident_context)
                    current_tokens += len(incident_context)

        # 2. 检索相关知识
        if include_knowledge:
            knowledge = await self.query_knowledge(user_query, top_k=3)
            if knowledge:
                knowledge_context = self._format_knowledge(knowledge)
                if current_tokens + len(knowledge_context) < original_max:
                    context_parts.append(knowledge_context)
                    current_tokens += len(knowledge_context)

        # 3. 检索会话上下文（向量存储 - 备用）
        if include_session and session_id:
            session_contexts = await self.recall_session_context(session_id, user_query, top_k=5)
            if session_contexts:
                session_context = self._format_session_context(session_contexts)
                if current_tokens + len(session_context) < original_max:
                    context_parts.append(session_context)

        return "\n\n".join(context_parts) if context_parts else ""

    def _format_incidents(self, incidents: List[Dict]) -> str:
        """格式化故障记忆"""
        parts = ["## 相关历史故障"]
        for inc in incidents:
            parts.append(f"\n### {inc['title'] or inc['incident_type']}")
            parts.append(f"**相似度**: {inc['similarity']:.0%}")
            parts.append(f"**内容**: {inc['content'][:200]}...")
            if inc.get('resolution'):
                parts.append(f"**解决方案**: {inc['resolution'][:200]}")
            if inc.get('root_cause'):
                parts.append(f"**根本原因**: {inc['root_cause'][:200]}")
        return "\n".join(parts)

    def _format_knowledge(self, knowledge: List[Dict]) -> str:
        """格式化知识库"""
        parts = ["## 相关知识"]
        for k in knowledge:
            category = k.get('category', 'general')
            title = k['title']
            parts.append(f"\n### [{category}] {title}")
            parts.append(f"**相似度**: {k['similarity']:.0%}")
            parts.append(f"**内容**: {k['content'][:300]}...")
            if k.get('tags'):
                tags = ", ".join(k['tags'])
                parts.append(f"**标签**: {tags}")
        return "\n".join(parts)

    def _format_session_context(self, contexts: List[Dict]) -> str:
        """格式化会话上下文"""
        parts = ["## 对话历史"]
        for ctx in contexts[:5]:  # 最多5条
            role = ctx['role']
            content = ctx['content'][:150]
            parts.append(f"- **{role}**: {content}...")
        return "\n".join(parts)

    # ==================== 自动学习 ====================

    async def auto_learn_from_result(
        self,
        user_query: str,
        result: dict,
        session_id: str = None,
        messages: List[Dict] = None
    ):
        """
        从执行结果自动学习（混合两层记忆）

        分层学习：
        1. Mem0: 自动提取用户偏好、对话上下文
        2. MemoryManager: 运维领域故障处理记录
        """
        settings = get_settings()

        # ===== Mem0 自动学习（通用对话记忆）=====
        if self._mem0_enabled and settings.MEM0_AUTO_LEARN and messages:
            try:
                # 添加用户级记忆（偏好、历史）
                await self._mem0_adapter.add_user_memory(
                    messages=messages,
                    metadata={"session_id": session_id}
                )

                # 添加会话级记忆
                if session_id:
                    await self._mem0_adapter.add_session_memory(
                        session_id=session_id,
                        messages=messages,
                        metadata={"timestamp": datetime.now().isoformat()}
                    )

                logger.info(f"🧠 Mem0: 自动学习完成")
            except Exception as e:
                logger.warning(f"⚠️ Mem0 自动学习失败: {e}")

        # ===== MemoryManager 自动学习（运维领域记忆）=====
        # 判断是否是故障处理
        if is_incident_handling(user_query):
            incident_type = self._detect_incident_type(user_query)
            title = self._extract_title(user_query)
            resolution = self._extract_resolution(result)
            root_cause = self._extract_root_cause(result)

            await self.remember_incident(
                content=user_query,
                incident_type=incident_type,
                title=title,
                resolution=resolution,
                root_cause=root_cause,
                metadata={
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat()
                }
            )
            logger.info(f"🤖 自动学习故障处理: {title}")

    # ==================== Mem0 对话记忆便捷方法 ====================

    async def add_conversation_memory(
        self,
        messages: List[Dict],
        session_id: str = None,
        user_only: bool = False
    ):
        """
        添加对话记忆到 Mem0

        Args:
            messages: 对话消息列表
            session_id: 会话 ID
            user_only: 是否只添加用户级记忆（不添加会话级）
        """
        if not self._mem0_enabled:
            return

        try:
            # 用户级记忆
            await self._mem0_adapter.add_user_memory(messages)

            # 会话级记忆
            if not user_only and session_id:
                await self._mem0_adapter.add_session_memory(
                    session_id=session_id,
                    messages=messages
                )

        except Exception as e:
            logger.warning(f"⚠️ 添加对话记忆失败: {e}")

    async def get_user_preferences(self) -> Dict[str, Any]:
        """获取用户偏好"""
        if not self._mem0_enabled:
            return {}

        try:
            return await self._mem0_adapter.extract_preferences([])
        except Exception as e:
            logger.warning(f"⚠️ 获取用户偏好失败: {e}")
            return {}

    def _detect_incident_type(self, query: str) -> str:
        """检测故障类型"""
        query_lower = query.lower()
        if any(kw in query_lower for kw in ["k8s", "kubernetes", "pod", "容器", "deployment"]):
            return "kubernetes"
        elif any(kw in query_lower for kw in ["mysql", "redis", "postgres", "mongodb", "数据库"]):
            return "database"
        elif any(kw in query_lower for kw in ["nginx", "服务", "接口", "api", "http"]):
            return "service"
        elif any(kw in query_lower for kw in ["磁盘", "内存", "cpu", "资源"]):
            return "resource"
        return "general"

    def _extract_title(self, query: str) -> str:
        """提取标题"""
        return query[:100]

    def _extract_resolution(self, result: dict) -> str:
        """提取解决方案"""
        if "messages" in result:
            last_message = result["messages"][-1]
            return last_message.get("content", "")[:500]
        elif "output" in result:
            return str(result["output"])[:500]
        return ""

    def _extract_root_cause(self, result: dict) -> str:
        """提取根本原因"""
        # 从结果中查找根因信息
        if "root_cause" in result:
            return result["root_cause"][:500]
        elif "diagnosis" in result:
            return str(result["diagnosis"])[:500]
        return ""

    async def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计"""
        vector_stats = await self.vector_store.get_memory_stats()
        return {
            "vector_store": vector_stats,
            "timestamp": datetime.now().isoformat()
        }


# 全局单例（按 user_id 隔离）
_memory_manager_instances: Dict[str, MemoryManager] = {}


def get_memory_manager(user_id: str = None) -> MemoryManager:
    """
    获取记忆管理器（按 user_id 隔离）

    Args:
        user_id: 用户 ID（默认为 None，使用默认实例）

    Returns:
        MemoryManager 实例
    """
    if user_id is None:
        user_id = "default_user"

    if user_id not in _memory_manager_instances:
        _memory_manager_instances[user_id] = MemoryManager(user_id=user_id)

    return _memory_manager_instances[user_id]



    
    def _estimate_tokens(self, text: str) -> int:
        """
        估算 Token 数量（参考 OpenClaw）
        
        规则：
        - 中文：约 1.5 字符/token
        - 英文：约 4 字符/token
        
        Args:
            text: 文本内容
        
        Returns:
            估算的 token 数量
        """
        if not text:
            return 0
        
        # 统计中文字符
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        
        # 统计英文和其他字符
        other_chars = len(text) - chinese_chars
        
        # 估算 token
        tokens = int(chinese_chars / 1.5 + other_chars / 4)
        
        return tokens
    
    def _truncate_to_token_limit(
        self,
        text: str,
        max_tokens: int,
        suffix: str = "\n...（已截断）"
    ) -> str:
        """
        截断文本到指定 Token 限制（参考 OpenClaw）
        
        Args:
            text: 原始文本
            max_tokens: 最大 token 数
            suffix: 截断后缀
        
        Returns:
            截断后的文本
        """
        if not text:
            return text
        
        current_tokens = self._estimate_tokens(text)
        
        if current_tokens <= max_tokens:
            return text
        
        # 估算字符数（保守估计）
        max_chars = int(max_tokens * 2)  # 保守估计 2 字符/token
        
        if len(text) <= max_chars:
            return text
        
        # 截断
        return text[:max_chars] + suffix

__all__ = [
    "MemoryManager",
    "get_memory_manager",
]
