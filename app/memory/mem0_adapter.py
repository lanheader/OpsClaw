"""
Mem0 适配器 - 通用对话记忆层

功能：
- 用户级记忆（User Level）: 跨会话持久化，用户偏好、历史记录
- 会话级记忆（Session Level）: 临时性，当前对话上下文
- 智能记忆提取: LLM 自动从对话中提取有价值信息
"""

import logging
import os
from typing import List, Dict, Optional, Any
from datetime import datetime

from app.core.llm_factory import LLMFactory
from app.core.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 尝试导入 mem0
try:
    from mem0 import Memory
    MEM0_AVAILABLE = True
    logger.info("✅ Mem0 可用")
except ImportError:
    MEM0_AVAILABLE = False
    logger.warning("⚠️ Mem0 不可用，通用对话记忆功能将被禁用")


class Mem0Adapter:
    """
    Mem0 适配器 - 通用对话记忆层

    负责：
    - 用户偏好记忆（喜欢简洁回答、关注特定指标等）
    - 会话上下文记忆（之前讨论过什么）
    - 智能记忆提取（自动从对话中提取有价值信息）

    不负责：
    - 运维领域记忆（由 MemoryManager 负责）
    """

    def __init__(
        self,
        user_id: str = None,
        api_key: str = None,
        provider: str = "openai",
        model: str = None
    ):
        """
        初始化 Mem0 适配器

        Args:
            user_id: 用户 ID（用于多用户隔离）
            api_key: Mem0 Platform API Key（可选，使用托管服务）
            provider: LLM 提供商（openai, ollama 等）
            model: 模型名称
        """
        if not MEM0_AVAILABLE:
            logger.warning("Mem0 不可用，记忆功能将被禁用")
            self.enabled = False
            return

        self.enabled = True
        self.user_id = user_id or "default_user"
        self._memory_client = None
        self.api_key = api_key
        self.provider = provider
        self.model = model

        logger.info(f"🧠 Mem0 适配器初始化 | user_id={self.user_id}")

    @property
    def client(self):
        """懒加载 Mem0 客户端"""
        if self._memory_client is None:
            self._memory_client = self._create_client()
        return self._memory_client

    def _create_client(self):
        """创建 Mem0 客户端（使用主 agent 相同的模型配置）"""
        settings = get_settings()

        # 如果提供了 API Key，使用托管平台
        if self.api_key:
            logger.info("使用 Mem0 托管平台")
            return Memory.from_api(
                api_key=self.api_key,
                user_id=self.user_id
            )

        # 使用自托管模式，复用主 agent 的模型配置
        provider = self.provider or settings.DEFAULT_LLM_PROVIDER

        # 构建配置
        config = {
            "user_id": self.user_id,
            "custom_prompts": {
                "system_prompt": """你是一个运维 AI 助手的记忆提取专家。
你的任务是从用户对话中提取有价值的信息，包括：
1. 用户偏好（如：喜欢详细解释、关注特定指标）
2. 上下文信息（如：正在排查某个服务的问题）
3. 重要决策（如：选择了某种解决方案）

只提取重要信息，忽略闲聊内容。"""
            }
        }

        # 根据 provider 配置 LLM（复用主 agent 的配置）
        if provider == "openai":
            if not settings.OPENAI_API_KEY:
                logger.warning("⚠️ OpenAI API Key 未配置，Mem0 将使用默认配置")
                # 使用默认配置
                config["llm"] = {
                    "provider": "openai",
                    "config": {
                        "model": "gpt-4o-mini",
                        "temperature": 0.1,
                        "max_tokens": 1000
                    }
                }
            else:
                config["llm"] = {
                    "provider": "openai",
                    "config": {
                        "model": self.model or settings.OPENAI_MODEL,
                        "temperature": 0.1,  # 记忆提取使用低温度
                        "max_tokens": 1000,
                        "api_key": settings.OPENAI_API_KEY,
                        "openai_base_url": settings.OPENAI_BASE_URL
                    }
                }
                logger.info(f"Mem0 使用 OpenAI: {settings.OPENAI_MODEL}")

        elif provider == "ollama":
            config["llm"] = {
                "provider": "ollama",
                "config": {
                    "model": self.model or settings.OLLAMA_MODEL,
                    "temperature": 0.1,
                    "ollama_base_url": settings.OLLAMA_BASE_URL
                }
            }
            logger.info(f"Mem0 使用 Ollama: {settings.OLLAMA_MODEL}")

        elif provider == "claude":
            if not settings.CLAUDE_API_KEY:
                logger.warning("⚠️ Claude API Key 未配置，Mem0 将回退到 OpenAI")
                # 回退到 OpenAI
                config["llm"] = {
                    "provider": "openai",
                    "config": {
                        "model": "gpt-4o-mini",
                        "temperature": 0.1
                    }
                }
            else:
                # Mem0 可能不直接支持 Claude，使用 OpenAI 兼容格式
                config["llm"] = {
                    "provider": "openai",  # Claude 通过 Anthropic API
                    "config": {
                        "model": self.model or settings.CLAUDE_MODEL,
                        "temperature": 0.1,
                        "api_key": settings.CLAUDE_API_KEY
                    }
                }
                logger.info(f"Mem0 使用 Claude: {settings.CLAUDE_MODEL}")

        elif provider == "zhipu":
            if not settings.ZHIPU_API_KEY:
                logger.warning("⚠️ Zhipu API Key 未配置，Mem0 将回退到 OpenAI")
                config["llm"] = {
                    "provider": "openai",
                    "config": {"model": "gpt-4o-mini", "temperature": 0.1}
                }
            else:
                # Zhipu 使用 OpenAI 兼容格式
                config["llm"] = {
                    "provider": "openai",
                    "config": {
                        "model": self.model or settings.ZHIPU_MODEL,
                        "temperature": 0.1,
                        "api_key": settings.ZHIPU_API_KEY,
                        "openai_base_url": "https://open.bigmodel.cn/api/paas/v4/"
                    }
                }
                logger.info(f"Mem0 使用 Zhipu: {settings.ZHIPU_MODEL}")

        else:
            # 未知 provider，使用默认 OpenAI
            logger.warning(f"⚠️ 未知的 LLM provider: {provider}，使用默认 OpenAI")
            config["llm"] = {
                "provider": "openai",
                "config": {
                    "model": "gpt-4o-mini",
                    "temperature": 0.1
                }
            }

        # 配置向量存储（使用 Qdrant 本地存储）
        qdrant_path = os.path.join(os.getcwd(), "data", "qdrant")
        config["vector_store"] = {
            "provider": "qdrant",
            "config": {
                "path": qdrant_path,
                "collection_name": f"mem0_ops_agent_{self.user_id}"
            }
        }

        logger.info(f"创建 Mem0 客户端 | provider={provider}")
        return Memory.from_config(config)

    # ==================== 用户级记忆 ====================

    async def add_user_memory(
        self,
        messages: List[Dict[str, str]],
        metadata: Dict[str, Any] = None
    ) -> List[Dict]:
        """
        添加用户级记忆（跨会话持久化）

        适用于：
        - 用户偏好（喜欢简洁/详细回答）
        - 长期关注点（持续监控某个服务）
        - 历史决策（之前选择的解决方案）

        Args:
            messages: 对话消息列表
            metadata: 额外元数据

        Returns:
            提取的记忆列表
        """
        if not self.enabled:
            return []

        try:
            result = self.client.add(
                messages=messages,
                user_id=self.user_id,
                metadata=metadata or {"timestamp": datetime.now().isoformat()}
            )

            logger.info(f"📝 Mem0: 添加了 {len(result)} 条用户记忆")
            return result

        except Exception as e:
            logger.error(f"❌ Mem0 添加记忆失败: {e}")
            return []

    async def search_user_memory(
        self,
        query: str,
        limit: int = 3
    ) -> List[Dict]:
        """
        搜索用户级记忆

        Args:
            query: 查询文本
            limit: 返回数量

        Returns:
            相关记忆列表
        """
        if not self.enabled:
            return []

        try:
            result = self.client.search(
                query=query,
                user_id=self.user_id,
                limit=limit
            )

            memories = result.get("results", [])
            logger.info(f"🔍 Mem0: 检索到 {len(memories)} 条用户记忆")
            return memories

        except Exception as e:
            logger.error(f"❌ Mem0 搜索记忆失败: {e}")
            return []

    async def get_all_user_memories(self) -> List[Dict]:
        """获取所有用户记忆"""
        if not self.enabled:
            return []

        try:
            result = self.client.get_all(user_id=self.user_id)
            return result.get("results", [])
        except Exception as e:
            logger.error(f"❌ Mem0 获取记忆失败: {e}")
            return []

    # ==================== 会话级记忆 ====================

    async def add_session_memory(
        self,
        session_id: str,
        messages: List[Dict[str, str]],
        metadata: Dict[str, Any] = None
    ) -> List[Dict]:
        """
        添加会话级记忆（临时性）

        适用于：
        - 当前对话的上下文
        - 临时状态（正在排查某个问题）
        - 对话历史摘要

        Args:
            session_id: 会话 ID
            messages: 对话消息列表
            metadata: 额外元数据

        Returns:
            提取的记忆列表
        """
        if not self.enabled:
            return []

        try:
            # 使用 session_id 作为 user_id 的子标识
            memory_user_id = f"{self.user_id}:session:{session_id}"

            result = self.client.add(
                messages=messages,
                user_id=memory_user_id,
                metadata={
                    **(metadata or {}),
                    "session_id": session_id,
                    "memory_level": "session",
                    "timestamp": datetime.now().isoformat()
                }
            )

            logger.info(f"📝 Mem0: 添加了 {len(result)} 条会话记忆 (session={session_id})")
            return result

        except Exception as e:
            logger.error(f"❌ Mem0 添加会话记忆失败: {e}")
            return []

    async def search_session_memory(
        self,
        session_id: str,
        query: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        搜索会话级记忆

        Args:
            session_id: 会话 ID
            query: 查询文本
            limit: 返回数量

        Returns:
            相关记忆列表
        """
        if not self.enabled:
            return []

        try:
            memory_user_id = f"{self.user_id}:session:{session_id}"

            result = self.client.search(
                query=query,
                user_id=memory_user_id,
                limit=limit
            )

            memories = result.get("results", [])
            logger.info(f"🔍 Mem0: 检索到 {len(memories)} 条会话记忆")
            return memories

        except Exception as e:
            logger.error(f"❌ Mem0 搜索会话记忆失败: {e}")
            return []

    # ==================== 记忆管理 ====================

    async def update_memory(self, memory_id: str, new_memory: str) -> bool:
        """更新记忆"""
        if not self.enabled:
            return False

        try:
            self.client.update(memory_id, new_memory)
            logger.info(f"✏️ Mem0: 更新记忆 {memory_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Mem0 更新记忆失败: {e}")
            return False

    async def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        if not self.enabled:
            return False

        try:
            self.client.delete(memory_id)
            logger.info(f"🗑️ Mem0: 删除记忆 {memory_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Mem0 删除记忆失败: {e}")
            return False

    # ==================== 实用方法 ====================

    async def extract_preferences(
        self,
        messages: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        从对话中提取用户偏好

        返回：
            {
                "response_style": "concise",  # concise / detailed
                "focus_areas": ["k8s", "performance"],
                "preferred_metrics": ["cpu", "memory"],
                ...
            }
        """
        if not self.enabled:
            return {}

        # 先搜索已有的偏好记忆
        existing = await self.search_user_memory(
            query="用户偏好 回答风格",
            limit=3
        )

        preferences = {}
        for memory in existing:
            content = memory.get("memory", "")
            # 简单解析（实际可以更复杂）
            if "简洁" in content or "简短" in content:
                preferences["response_style"] = "concise"
            elif "详细" in content:
                preferences["response_style"] = "detailed"

        return preferences

    async def get_context_for_query(
        self,
        query: str,
        session_id: str = None,
        include_user: bool = True,
        include_session: bool = True,
        max_tokens: int = 1000
    ) -> str:
        """
        为查询构建记忆上下文

        Args:
            query: 用户查询
            session_id: 会话 ID
            include_user: 是否包含用户级记忆
            include_session: 是否包含会话级记忆
            max_tokens: 最大 token 数

        Returns:
            格式化的上下文字符串
        """
        if not self.enabled:
            return ""

        context_parts = []
        current_tokens = 0

        # 1. 用户级记忆（偏好、历史）
        if include_user:
            user_memories = await self.search_user_memory(query, limit=2)
            if user_memories:
                user_context = self._format_memories(user_memories, "用户偏好")
                if current_tokens + len(user_context) < max_tokens:
                    context_parts.append(user_context)
                    current_tokens += len(user_context)

        # 2. 会话级记忆（当前对话上下文）
        if include_session and session_id:
            session_memories = await self.search_session_memory(session_id, query, limit=3)
            if session_memories:
                session_context = self._format_memories(session_memories, "对话上下文")
                if current_tokens + len(session_context) < max_tokens:
                    context_parts.append(session_context)
                    current_tokens += len(session_context)

        return "\n\n".join(context_parts)

    def _format_memories(self, memories: List[Dict], title: str) -> str:
        """格式化记忆列表"""
        if not memories:
            return ""

        parts = [f"## {title}"]
        for memory in memories:
            content = memory.get("memory", "")
            score = memory.get("score", 0)
            parts.append(f"- {content} (相关度: {score:.0%})")

        return "\n".join(parts)


# 全局单例（按 user_id 隔离）
_mem0_adapters: Dict[str, Mem0Adapter] = {}


def get_mem0_adapter(
    user_id: str = None,
    api_key: str = None,
    provider: str = None,
    model: str = None
) -> Mem0Adapter:
    """
    获取 Mem0 适配器（按 user_id 缓存）

    Args:
        user_id: 用户 ID
        api_key: Mem0 Platform API Key（可选）
        provider: LLM 提供商
        model: 模型名称

    Returns:
        Mem0Adapter 实例
    """
    user_id = user_id or "default_user"
    cache_key = f"{user_id}:{provider or 'default'}:{model or 'default'}"

    if cache_key not in _mem0_adapters:
        _mem0_adapters[cache_key] = Mem0Adapter(
            user_id=user_id,
            api_key=api_key,
            provider=provider,
            model=model
        )

    return _mem0_adapters[cache_key]


__all__ = [
    "Mem0Adapter",
    "get_mem0_adapter",
    "MEM0_AVAILABLE",
]
