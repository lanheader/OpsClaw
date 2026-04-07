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

from app.utils.logger import get_logger, get_request_context

logger = get_logger(__name__)


def _extract_model_metadata(model: Any) -> tuple[str, str]:
    """提取模型 provider / model 元数据，优先使用工厂注入的诊断字段。"""
    provider = getattr(model, "_ops_provider", "unknown")
    model_name = getattr(model, "_ops_model", None)

    if not model_name:
        model_name = getattr(model, "model_name", None) or getattr(model, "model", None) or "unknown"

    if provider == "unknown":
        class_name = type(model).__name__.lower()
        if "openai" in class_name:
            provider = "openai"
        elif "anthropic" in class_name or "claude" in class_name:
            provider = "claude"
        elif "zhipu" in class_name:
            provider = "zhipu"
        elif "ollama" in class_name:
            provider = "ollama"
        elif "router" in class_name:
            provider = "openrouter"

    return str(provider), str(model_name)


class LoggingMiddleware(AgentMiddleware):
    """日志中间件 - 记录模型调用、工具执行和耗时（支持请求追踪）"""

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

        # 获取请求上下文
        ctx = get_request_context()
        session_id = ctx.get('session_id', 'no-sess')

        logger.info(
            f"🤖 [{session_id}] [{agent_name}] LLM 调用开始 | 消息数={msg_count} | 最后一条: {last_preview!r}"
        )
        start = time.time()

        try:
            response = await handler(request)
        except Exception as exc:
            elapsed = time.time() - start
            provider, model_name = _extract_model_metadata(request.model)
            logger.error(
                f"❌ [{session_id}] [{agent_name}] LLM 调用失败 | 耗时={elapsed:.2f}s | "
                f"provider={provider} | model={model_name} | {type(exc).__name__}: {exc}"
            )
            raise

        elapsed = time.time() - start
        ai_msg = response.result[0] if response.result else None
        tool_calls = getattr(ai_msg, "tool_calls", []) if ai_msg else []
        raw_content = getattr(ai_msg, "content", "") if ai_msg else ""
        # content 可能是 list（多模态）或 str
        if isinstance(raw_content, list):
            content_text = " ".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in raw_content
            ).strip()
        else:
            content_text = str(raw_content).strip()
        content_preview = content_text[:80]
        provider, model_name = _extract_model_metadata(request.model)

        if tool_calls:
            tools_info = ", ".join(
                f"{tc.get('name', '?')}({list(tc.get('args', {}).keys())})" for tc in tool_calls
            )
            logger.info(
                f"✅ [{session_id}] [{agent_name}] LLM 完成 | 耗时={elapsed:.2f}s | 工具调用: {tools_info}"
            )
        elif not content_text:
            # 空响应可能是正常的（DeepAgents 内部调用），降级为 WARNING
            # 框架会从消息历史中提取最终结果，不一定是错误
            logger.warning(
                f"⚠️ [{session_id}] [{agent_name}] LLM 返回空内容 | 耗时={elapsed:.2f}s | "
                f"provider={provider} | model={model_name} | 消息数={msg_count} | "
                f"说明: 可能是框架内部调用，最终结果会从消息历史提取"
            )
        else:
            logger.info(
                f"✅ [{session_id}] [{agent_name}] LLM 完成 | 耗时={elapsed:.2f}s | 回复: {content_preview!r}"
            )

        return response

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage]],  # type: ignore[override]
    ) -> ToolMessage:
        """拦截工具调用，记录工具名、参数和耗时"""
        tool_name = request.tool_call.get("name", "unknown")
        tool_args = request.tool_call.get("args", {})

        # 获取请求上下文
        ctx = get_request_context()
        session_id = ctx.get('session_id', 'no-sess')

        # 检测是否是 subagent 调用
        is_subagent = tool_name == "task"
        subagent_name = tool_args.get("subagent_type", tool_args.get("subagent", "unknown")) if is_subagent else None
        task_description = tool_args.get("description", tool_args.get("task", ""))[:80] if is_subagent else ""

        args_preview = {k: str(v)[:60] for k, v in tool_args.items()}

        if is_subagent:
            logger.info(
                f"🎯 [{session_id}] [SubAgent 开始] {subagent_name} | 任务: {task_description}"
            )
        else:
            logger.info(f"🔧 [{session_id}] [工具开始] {tool_name} | 参数: {args_preview}")

        start = time.time()

        try:
            result = await handler(request)
        except Exception as exc:
            elapsed = time.time() - start
            if is_subagent:
                logger.error(
                    f"❌ [{session_id}] [SubAgent 失败] {subagent_name} | 耗时={elapsed:.2f}s | {type(exc).__name__}: {exc}"
                )
            else:
                logger.error(
                    f"❌ [{session_id}] [工具失败] {tool_name} | 耗时={elapsed:.2f}s | {type(exc).__name__}: {exc}"
                )
            raise

        elapsed = time.time() - start
        result_preview = str(getattr(result, "content", ""))[:100]

        if is_subagent:
            logger.info(
                f"✅ [{session_id}] [SubAgent 完成] {subagent_name} | 耗时={elapsed:.2f}s | 结果: {result_preview!r}"
            )
        else:
            logger.info(
                f"✅ [{session_id}] [工具完成] {tool_name} | 耗时={elapsed:.2f}s | 结果: {result_preview!r}"
            )

        return result
