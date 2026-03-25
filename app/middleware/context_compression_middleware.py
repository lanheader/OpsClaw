# app/middleware/context_compression_middleware.py
"""
上下文压缩中间件

解决历史消息过长导致的截断问题：
1. 保留最近 N 条完整消息
2. 对更早的消息生成压缩摘要
3. 摘要保留关键信息：用户意图、实体、决策、结论
"""

from typing import Any, List, Optional
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.utils.logger import get_logger

logger = get_logger(__name__)

# 配置
MAX_FULL_MESSAGES = 20  # 保留最近 20 条完整消息
COMPRESSION_THRESHOLD = 30  # 超过 30 条消息时触发压缩
SUMMARY_BLOCK_SIZE = 10  # 每 10 条消息生成一个摘要


class ContextCompressionMiddleware(AgentMiddleware):
    """
    上下文压缩中间件

    策略：
    1. 如果消息数 < COMPRESSION_THRESHOLD：不压缩
    2. 如果消息数 >= COMPRESSION_THRESHOLD：
       - 保留最近 MAX_FULL_MESSAGES 条完整消息
       - 对更早的消息按 SUMMARY_BLOCK_SIZE 分组生成摘要
    """

    def __init__(self, max_full_messages: int = MAX_FULL_MESSAGES):
        self.max_full_messages = max_full_messages
        self._summary_cache: dict[str, str] = {}  # 摘要缓存
        logger.info(f"✅ 上下文压缩中间件已启用，保留最近 {max_full_messages} 条完整消息")

    async def awrap_model_call(self, request, handler):
        """在 LLM 调用前压缩上下文"""
        messages = request.messages
        original_count = len(messages)

        if original_count < COMPRESSION_THRESHOLD:
            return await handler(request)

        # 压缩消息
        compressed_messages = await self._compress_messages(messages)
        request.messages = compressed_messages

        logger.info(
            f"📉 上下文压缩: {original_count} → {len(compressed_messages)} 条消息"
        )

        return await handler(request)

    async def _compress_messages(self, messages: List[Any]) -> List[Any]:
        """压缩消息列表"""
        # 保留最近的消息（完整）
        recent_messages = messages[-self.max_full_messages:]
        older_messages = messages[:-self.max_full_messages]

        if not older_messages:
            return messages

        # 对早期消息生成摘要
        summary = await self._generate_summary(older_messages)

        # 构建压缩后的消息列表
        compressed = []

        # 添加摘要作为系统消息
        if summary:
            compressed.append(SystemMessage(
                content=f"[历史对话摘要]\n{summary}\n\n--- 以下是最近的对话 ---"
            ))

        # 添加最近的完整消息
        compressed.extend(recent_messages)

        return compressed

    async def _generate_summary(self, messages: List[Any]) -> Optional[str]:
        """
        生成对话摘要

        提取关键信息：
        1. 用户的主要意图和需求
        2. 涉及的关键实体（集群名、服务名等）
        3. 重要的决策和结论
        4. 待解决的问题或任务
        """
        if not messages:
            return None

        # 提取关键信息
        intents = []
        entities = set()
        decisions = []
        pending_tasks = []

        for msg in messages:
            content = str(getattr(msg, "content", ""))

            # 提取用户意图
            if isinstance(msg, HumanMessage):
                # 简单提取：取前 100 字符作为意图描述
                intent_preview = content[:100].strip()
                if intent_preview:
                    intents.append(intent_preview)

            # 提取 AI 决策和结论
            elif isinstance(msg, AIMessage):
                # 查找关键结论标记
                if any(kw in content for kw in ["结论", "建议", "原因", "结果", "发现"]):
                    # 提取包含关键词的句子
                    for sentence in content.split("。"):
                        if any(kw in sentence for kw in ["结论", "建议", "原因", "结果", "发现"]):
                            decisions.append(sentence.strip()[:200])
                            break

        # 构建摘要
        summary_parts = []

        if intents:
            # 只保留最后 5 个意图（最近的更相关）
            recent_intents = intents[-5:]
            summary_parts.append(f"用户需求: {recent_intents[-1] if recent_intents else '未知'}")

        if decisions:
            # 只保留最后 3 个决策
            recent_decisions = decisions[-3:]
            summary_parts.append(f"关键结论: {'; '.join(recent_decisions)}")

        if not summary_parts:
            # 如果没有提取到关键信息，生成简单摘要
            human_count = sum(1 for m in messages if isinstance(m, HumanMessage))
            summary_parts.append(f"之前进行了 {human_count} 轮对话")

        return "\n".join(summary_parts)

    async def awrap_tool_call(self, request, handler):
        """工具调用不需要压缩"""
        return await handler(request)


# 便捷函数
def create_compression_middleware(max_full_messages: int = MAX_FULL_MESSAGES) -> ContextCompressionMiddleware:
    """创建上下文压缩中间件"""
    return ContextCompressionMiddleware(max_full_messages=max_full_messages)
