"""
DeepAgents 日志中间件
记录模型调用、工具执行和耗时，方便定位问题
"""

import time
from typing import Any, Awaitable, Callable

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain_core.messages import AIMessage, ToolMessage

from app.utils.logger import get_logger

logger = get_logger(__name__)


class LoggingMiddleware(AgentMiddleware):
    """日志中间件 - 记录模型调用、工具执行和耗时"""

    @property
    def name(self) -> str:
        return "LoggingMiddleware"

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse | AIMessage:
        """拦截模型调用，记录输入消息数、工具调用和耗时"""
        msg_count = len(request.messages)
        last_msg = request.messages[-1] if request.messages else None
        last_preview = str(getattr(last_msg, "content", ""))[:80] if last_msg else ""

        # 尝试从 runtime 中获取当前 agent 名称
        agent_name = "主智能体"
        try:
            if hasattr(request, "runtime") and request.runtime:
                runtime_info = getattr(request.runtime, "agent_name", None)
                if runtime_info:
                    agent_name = runtime_info
        except Exception:
            pass

        print(
            f"[LoggingMiddleware] 🤖 [{agent_name}] LLM 调用开始 | 消息数={msg_count} | {last_preview!r}",
            flush=True,
        )
        logger.info(
            f"🤖 [{agent_name}] LLM 调用开始 | 消息数={msg_count} | 最后一条: {last_preview!r}"
        )
        start = time.time()

        try:
            response = await handler(request)
        except Exception as exc:
            elapsed = time.time() - start
            logger.error(
                f"❌ [{agent_name}] LLM 调用失败 | 耗时={elapsed:.2f}s | {type(exc).__name__}: {exc}"
            )
            raise

        elapsed = time.time() - start
        ai_msg = response.result[0] if response.result else None
        tool_calls = getattr(ai_msg, "tool_calls", []) if ai_msg else []
        content_preview = str(getattr(ai_msg, "content", ""))[:80] if ai_msg else ""

        if tool_calls:
            tools_info = ", ".join(
                f"{tc.get('name', '?')}({list(tc.get('args', {}).keys())})" for tc in tool_calls
            )
            logger.info(
                f"✅ [{agent_name}] LLM 完成 | 耗时={elapsed:.2f}s | 工具调用: {tools_info}"
            )
            print(
                f"[LoggingMiddleware] ✅ [{agent_name}] LLM 完成 | 耗时={elapsed:.2f}s | 工具: {tools_info}",
                flush=True,
            )
        else:
            logger.info(
                f"✅ [{agent_name}] LLM 完成 | 耗时={elapsed:.2f}s | 回复: {content_preview!r}"
            )
            print(
                f"[LoggingMiddleware] ✅ [{agent_name}] LLM 完成 | 耗时={elapsed:.2f}s", flush=True
            )

        return response

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage]],
    ) -> ToolMessage:
        """拦截工具调用，记录工具名、参数和耗时"""
        tool_name = request.tool_call.get("name", "unknown")
        tool_args = request.tool_call.get("args", {})

        # 检测是否是 subagent 调用
        is_subagent = tool_name == "task"
        subagent_name = tool_args.get("subagent_type", tool_args.get("subagent", "unknown")) if is_subagent else None
        task_description = tool_args.get("description", tool_args.get("task", ""))[:80] if is_subagent else ""

        # 只显示参数的 key 和值的简短预览，避免日志过长
        args_preview = {k: str(v)[:60] for k, v in tool_args.items()}

        # ========== 工具调用开始 ==========
        if is_subagent:
            logger.info(
                f"🎯 [SubAgent 开始] {subagent_name} | 任务: {task_description}"
            )
            print(
                f"[LoggingMiddleware] 🎯 [SubAgent 开始] {subagent_name}",
                flush=True,
            )
        else:
            logger.info(f"🔧 [工具开始] {tool_name} | 参数: {args_preview}")
            print(f"[LoggingMiddleware] 🔧 [工具开始] {tool_name} | {args_preview}", flush=True)

        start = time.time()

        try:
            result = await handler(request)
        except Exception as exc:
            elapsed = time.time() - start
            if is_subagent:
                logger.error(
                    f"❌ [SubAgent 失败] {subagent_name} | 耗时={elapsed:.2f}s | {type(exc).__name__}: {exc}"
                )
                print(f"[LoggingMiddleware] ❌ [SubAgent 失败] {subagent_name} | 耗时={elapsed:.2f}s", flush=True)
            else:
                logger.error(
                    f"❌ [工具失败] {tool_name} | 耗时={elapsed:.2f}s | {type(exc).__name__}: {exc}"
                )
                print(f"[LoggingMiddleware] ❌ [工具失败] {tool_name} | 耗时={elapsed:.2f}s", flush=True)
            raise

        elapsed = time.time() - start
        result_preview = str(getattr(result, "content", ""))[:100]

        # ========== 工具调用结束 ==========
        if is_subagent:
            logger.info(
                f"✅ [SubAgent 完成] {subagent_name} | 耗时={elapsed:.2f}s | 结果: {result_preview!r}"
            )
            print(
                f"[LoggingMiddleware] ✅ [SubAgent 完成] {subagent_name} | 耗时={elapsed:.2f}s",
                flush=True,
            )
        else:
            logger.info(
                f"✅ [工具完成] {tool_name} | 耗时={elapsed:.2f}s | 结果: {result_preview!r}"
            )
            print(f"[LoggingMiddleware] ✅ [工具完成] {tool_name} | 耗时={elapsed:.2f}s", flush=True)

        return result
