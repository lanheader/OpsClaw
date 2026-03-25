"""
记忆中间件 - 自动增强上下文

功能：
- 自动检索相关记忆
- 增强用户输入
- 自动学习处理结果
"""

import logging
from typing import List, Dict, Any, Optional

from app.memory.memory_manager import get_memory_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)


class MemoryMiddleware:
    """记忆中间件 - 自动增强上下文"""

    def __init__(self, enable_auto_learn: bool = True):
        self.memory_manager = None
        self.enable_auto_learn = enable_auto_learn

    async def process_input(
        self,
        messages: List[Dict[str, Any]],
        session_id: str = None,
        config: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        处理输入消息（已禁用自动注入）
        
        ⚠️ 参考 OpenClaw 设计：
        - 不自动注入记忆到输入
        - 记忆检索改为按需调用 memory_search
        - 由 Subagent 自主决定是否使用记忆

        Args:
            messages: 原始消息列表
            session_id: 会话 ID
            config: 额外配置

        Returns:
            原始消息列表（不增强）
        """
        # ❌ 不再自动注入记忆！
        # 原因：参考 OpenClaw 的检索式访问设计
        # 改进：Subagent 应该按需调用 memory_search
        
        return messages

    async def process_output(
        self,
        messages: List[Dict[str, Any]],
        session_id: str = None,
        user_query: str = None,
        conversation_messages: List[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        处理输出消息 - 自动学习处理结果

        Args:
            messages: 输出消息列表
            session_id: 会话 ID
            user_query: 原始用户查询
            conversation_messages: 完整对话消息（用于 Mem0 学习）

        Returns:
            处理后的消息列表
        """
        if not self.enable_auto_learn:
            return messages

        if not user_query or not session_id:
            return messages

        # 懒加载记忆管理器
        if self.memory_manager is None:
            self.memory_manager = get_memory_manager()

        # 构建结果对象
        result = {"messages": messages}

        # 自动学习（包含 Mem0 和 MemoryManager）
        await self.memory_manager.auto_learn_from_result(
            user_query=user_query,
            result=result,
            session_id=session_id,
            messages=conversation_messages  # 传递完整对话给 Mem0
        )

        return messages

    async def store_message(
        self,
        session_id: str,
        role: str,
        content: str,
        importance: float = 0.5
    ):
        """存储消息到会话记忆"""
        if self.memory_manager is None:
            self.memory_manager = get_memory_manager()

        await self.memory_manager.remember_message(
            session_id=session_id,
            role=role,
            content=content,
            importance=importance
        )


class MemoryEnhancedAgent:
    """
    记忆增强的 Agent 包装器

    为任何 Agent 添加记忆能力
    """

    def __init__(
        self,
        agent,
        enable_memory: bool = True,
        enable_auto_learn: bool = True
    ):
        """
        Args:
            agent: 原始 agent
            enable_memory: 是否启用记忆增强
            enable_auto_learn: 是否启用自动学习
        """
        self.agent = agent
        self.enable_memory = enable_memory
        self.enable_auto_learn = enable_auto_learn
        self.memory_manager = None

        if enable_memory:
            self.memory_manager = get_memory_manager()

    async def ainvoke(self, input_data, config=None, **kwargs):
        """增强的 invoke 方法"""
        session_id = config.get("configurable", {}).get("thread_id") if config else None

        # 提取用户查询
        user_query = self._extract_user_query(input_data)

        # 构建增强输入
        if self.enable_memory and user_query:
            # 检索相关记忆
            context = await self.memory_manager.build_context(
                user_query=user_query,
                session_id=session_id,
                include_incidents=True,
                include_knowledge=True
            )

            if context:
                # 增强输入
                enhanced_input = f"{user_query}\n\n参考资料（来自历史记录和知识库）：\n{context}"
                input_data = self._update_input_query(input_data, enhanced_input)
                logger.info(f"🧠 [MemoryEnhancedAgent] 输入已增强")

        # 调用原始 agent
        result = await self.agent.ainvoke(input_data, config=config, **kwargs)

        # 自动学习
        if self.enable_auto_learn and user_query and session_id:
            await self.memory_manager.auto_learn_from_result(
                user_query=user_query,
                result=result,
                session_id=session_id
            )

        return result

    async def astream(self, input_data, config=None, **kwargs):
        """
        增强的 stream 方法（已禁用自动注入）
        
        ⚠️ 参考 OpenClaw 设计：
        - 不自动注入记忆到输入
        - 记忆检索改为按需调用 memory_search
        - 由 Subagent 自主决定是否使用记忆
        """
        session_id = config.get("configurable", {}).get("thread_id") if config else None
        user_query = self._extract_user_query(input_data)

        # ❌ 不再自动注入记忆！
        # 原因：参考 OpenClaw 的检索式访问设计

        # 流式输出（不增强输入）
        async for chunk in self.agent.astream(input_data, config=config, **kwargs):
            yield chunk

        # 自动学习（在流式输出完成后）
        if self.enable_auto_learn and user_query and session_id:
            # 注意：流式输出后需要收集结果
            pass

    def _extract_user_query(self, input_data) -> Optional[str]:
        """从输入中提取用户查询"""
        if isinstance(input_data, dict):
            if "messages" in input_data:
                messages = input_data["messages"]
                if messages:
                    last_msg = messages[-1]
                    if isinstance(last_msg, dict):
                        return last_msg.get("content")
                    elif isinstance(last_msg, tuple) and len(last_msg) >= 2:
                        return last_msg[1]
            return input_data.get("query")
        return None

    def _update_input_query(self, input_data, enhanced_query: str):
        """更新输入中的查询"""
        if isinstance(input_data, dict):
            if "messages" in input_data:
                messages = input_data["messages"]
                if messages:
                    last_msg = messages[-1]
                    if isinstance(last_msg, dict):
                        messages[-1]["content"] = enhanced_query
                    elif isinstance(last_msg, tuple) and len(last_msg) >= 2:
                        messages[-1] = (last_msg[0], enhanced_query)
                return input_data
            elif "query" in input_data:
                input_data["query"] = enhanced_query
        return input_data


__all__ = [
    "MemoryMiddleware",
    "MemoryEnhancedAgent",
]
gent",
]
