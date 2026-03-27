# app/middleware/message_trimming_middleware.py
"""
消息截断中间件

防止历史消息过多导致 LLM 超时。
只保留最近的 N 条消息，避免 token 数量暴增。
"""

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage

from app.utils.logger import get_logger

logger = get_logger(__name__)

# 配置：保留最近的消息数量
MAX_MESSAGES_TO_KEEP = 20  # 保留最近 20 条消息（约 5-10 轮对话）
MIN_MESSAGES_TO_KEEP = 5   # 最少保留 5 条消息（约 2-3 轮对话）


class MessageTrimmingMiddleware(AgentMiddleware):
    """
    消息截断中间件（智能截断策略）

    在每次 LLM 调用前，自动截断历史消息，只保留：
    1. 系统提示词（始终保留，在 request.system_message 中）
    2. 最近的 N 条消息（用户消息 + AI 响应，在 request.messages 中）

    智能截断策略：
    - 优先保留完整的对话轮次（用户消息 + AI 响应成对保留）
    - 保留最近的用户消息（当前正在处理的）
    - 如果消息数量超限，从最旧的对话轮次开始删除

    这样可以防止：
    - 历史消息过多导致 LLM 超时
    - Token 数量暴增
    - 上下文窗口溢出

    同时尽量保持：
    - 对话的连贯性
    - 完整的对话轮次
    """

    def __init__(self, max_messages: int = MAX_MESSAGES_TO_KEEP):
        """
        初始化消息截断中间件

        Args:
            max_messages: 保留的最大消息数量（不包括系统提示词）
        """
        self.max_messages = max_messages
        logger.info(f"✅ 消息截断中间件已启用，保留最近 {max_messages} 条消息（智能截断）")

    async def awrap_model_call(self, request, handler):
        """
        在 LLM 调用前截断消息（智能截断）

        Args:
            request: ModelRequest 对象
            handler: 下一个处理器

        Returns:
            LLM 响应
        """
        messages = request.messages
        original_count = len(messages)

        if original_count == 0:
            return await handler(request)

        # 如果消息数量未超限，直接通过
        if original_count <= self.max_messages:
            logger.info(
                f"📊 消息数量: {original_count} 条（未超过限制 {self.max_messages}，无需截断）"
            )
            return await handler(request)

        # 智能截断：尽量保留完整的对话轮次
        trimmed_messages = self._smart_trim_messages(messages)
        request.messages = trimmed_messages

        logger.warning(
            f"⚠️ 消息数量过多 ({original_count} 条)，智能截断为 {len(trimmed_messages)} 条"
        )
        logger.info(
            f"📊 截断前: {original_count} 条消息 | "
            f"截断后: {len(trimmed_messages)} 条消息 | "
            f"保留了最近 {self._count_conversation_turns(trimmed_messages)} 轮对话"
        )

        # 调用下一个处理器
        return await handler(request)

    def _smart_trim_messages(self, messages: list) -> list:
        """
        智能截断消息，尽量保留完整的对话轮次

        策略：
        1. 从后往前遍历消息
        2. 优先保留完整的对话轮次（HumanMessage + AIMessage）
        3. 如果达到最大限制，停止保留

        Args:
            messages: 原始消息列表

        Returns:
            截断后的消息列表
        """
        # 从后往前遍历，保留完整的对话轮次
        kept_messages = []
        current_turn = []

        for msg in reversed(messages):
            current_turn.insert(0, msg)

            # 如果遇到 HumanMessage，说明一个完整的对话轮次结束
            if isinstance(msg, HumanMessage):
                # 检查是否超过限制
                if len(kept_messages) + len(current_turn) <= self.max_messages:
                    kept_messages = current_turn + kept_messages
                    current_turn = []
                else:
                    # 如果加上当前轮次会超限，检查是否至少保留了最少消息数
                    if len(kept_messages) >= MIN_MESSAGES_TO_KEEP:
                        break
                    else:
                        # 强制保留当前轮次，确保至少有最少消息数
                        kept_messages = current_turn + kept_messages
                        break

        # 如果还有未处理的消息（不完整的轮次），且消息数不足最少限制，也保留
        if current_turn and len(kept_messages) < MIN_MESSAGES_TO_KEEP:
            kept_messages = current_turn + kept_messages

        # 如果截断后消息数仍然超限，强制截断到最大限制
        if len(kept_messages) > self.max_messages:
            kept_messages = kept_messages[-self.max_messages :]

        return kept_messages

    def _count_conversation_turns(self, messages: list) -> int:
        """
        统计对话轮次数量

        Args:
            messages: 消息列表

        Returns:
            对话轮次数量
        """
        return sum(1 for msg in messages if isinstance(msg, HumanMessage))

    async def awrap_tool_call(self, request, handler):
        """
        工具调用不需要截断消息

        Args:
            request: 工具调用请求
            handler: 下一个处理器

        Returns:
            工具调用结果
        """
        return await handler(request)
