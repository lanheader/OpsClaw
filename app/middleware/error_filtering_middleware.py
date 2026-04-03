# app/middleware/error_filtering_middleware.py
"""
错误消息过滤中间件

过滤掉工具调用失败的错误消息，防止 LLM 在下一轮对话中对错误做出响应。

问题场景：
- LLM 调用不存在的工具（如 get_configmaps）
- 工具返回错误消息，被添加为 AIMessage
- 下一轮 LLM 调用看到错误消息并对其做出响应
- 结果：LLM 回复关于错误，而不是回答用户问题

解决方案：
- 在每次 LLM 调用前，过滤掉包含错误标记的 AIMessage
- 保留 HumanMessage 和正常的 AIMessage
"""

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, AIMessage

from app.utils.logger import get_logger

logger = get_logger(__name__)


class ErrorFilteringMiddleware(AgentMiddleware):
    """
    错误消息过滤中间件

    在每次 LLM 调用前，自动过滤掉包含错误标记的 AIMessage。

    过滤规则：
    1. AIMessage.content 以 "Error:" 开头
    2. AIMessage.content 包含 "is not a valid tool"
    3. AIMessage.content 包含 "Tool execution failed"

    保留：
    - HumanMessage（用户消息）
    - ToolMessage（工具返回）
    - 正常的 AIMessage（AI 响应）
    """

    # 错误标记列表
    ERROR_MARKERS = [
        "Error:",
        "is not a valid tool",
        "Tool execution failed",
        "tool not found",
        "invalid tool",
    ]

    def __init__(self):  # type: ignore[no-untyped-def]
        logger.info("✅ 错误消息过滤中间件已启用")

    async def awrap_model_call(self, request, handler):  # type: ignore[no-untyped-def]
        """
        在 LLM 调用前过滤错误消息

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

        # 过滤错误消息
        filtered_messages = self._filter_error_messages(messages)
        filtered_count = len(filtered_messages)

        if filtered_count < original_count:
            removed_count = original_count - filtered_count
            logger.warning(
                f"🧹 过滤了 {removed_count} 条错误消息 "
                f"({original_count} → {filtered_count})"
            )
            # 记录被过滤的消息内容（调试用）
            for msg in messages:
                if msg not in filtered_messages and isinstance(msg, AIMessage):
                    logger.debug(f"  过滤错误消息: {msg.content[:100]}...")

            request.messages = filtered_messages

        return await handler(request)

    def _filter_error_messages(self, messages: list) -> list:
        """
        过滤掉包含错误标记的 AIMessage

        Args:
            messages: 原始消息列表

        Returns:
            过滤后的消息列表
        """
        filtered = []

        for msg in messages:
            # 保留所有非 AIMessage
            if not isinstance(msg, AIMessage):
                filtered.append(msg)
                continue

            # 检查 AIMessage.content 是否包含错误标记
            if self._is_error_message(msg):
                # 跳过错误消息
                continue

            # 保留正常的 AIMessage
            filtered.append(msg)

        return filtered

    def _is_error_message(self, message: AIMessage) -> bool:
        """
        判断消息是否为错误消息

        Args:
            message: AIMessage 对象

        Returns:
            True 如果是错误消息，False 否则
        """
        if not message.content:
            return False

        content = message.content

        # 检查是否包含任何错误标记
        for marker in self.ERROR_MARKERS:
            if marker in content:
                return True

        return False

    async def awrap_tool_call(self, request, handler):  # type: ignore[no-untyped-def]
        """
        工具调用不需要过滤消息

        Args:
            request: 工具调用请求
            handler: 下一个处理器

        Returns:
            工具调用结果
        """
        return await handler(request)
