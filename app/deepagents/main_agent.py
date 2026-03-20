"""
DeepAgents 主智能体配置
负责任务规划、子智能体委派、批准流程和智能路由
"""

from deepagents import create_deep_agent
from langchain_core.language_models import BaseChatModel
from typing import Any, Optional, Set

from app.core.llm_factory import LLMFactory
from app.core.checkpointer import get_checkpointer
from app.core.tool_permission_mapper import filter_tools_by_permissions
from app.prompts.main_agent import MAIN_AGENT_SYSTEM_PROMPT
from app.deepagents.subagents import get_all_subagents
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.message_trimming_middleware import MessageTrimmingMiddleware
from app.tools import (
    get_k8s_tools,
    get_prometheus_tools,
    get_loki_tools,
    get_command_executor_tools,
    get_approval_tools,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 高风险工具列表（需要用户批准）
# 注意：只包含真正的高风险操作，只读查询不应该在这里
_HIGH_RISK_TOOLS = {
    # K8s 高风险操作（删除、重启、扩缩容）
    "delete_pod": True,
    "delete_deployment": True,
    "delete_service": True,
    "restart_deployment": True,
    "scale_deployment": True,
    "update_configmap": True,
    "update_secret": True,
    # 命令执行 - 暂时禁用，因为无法区分只读和写操作
    # TODO: 需要更精细的策略，或者分离只读和写操作工具
    # "execute_command": True,
    # "execute_kubectl_command": True,
}

# 单例 agent（所有会话共享同一个编译图，通过 thread_id 区分会话）
_agent: Optional[Any] = None


async def get_ops_agent(
    llm: Optional[BaseChatModel] = None,
    enable_approval: bool = True,
    user_permissions: Optional[Set[str]] = None,
) -> Any:
    """
    获取 Ops Agent 单例（懒加载，异步）

    所有会话共享同一个编译图，通过 checkpointer + thread_id 区分会话状态。
    checkpointer 由 CheckpointerFactory 管理，默认使用 SQLite 持久化。

    Args:
        llm: 语言模型实例 (默认使用 LLMFactory)
        enable_approval: 是否启用 interrupt_on 批准流程
        user_permissions: 用户权限代码集合，用于过滤可用工具

    Returns:
        编译后的 DeepAgents 图
    """
    global _agent

    # 注意：如果传入了 user_permissions，不使用缓存的 agent
    # 因为不同用户的权限不同，需要动态创建 agent
    if _agent is not None and user_permissions is None:
        return _agent

    if llm is None:
        # 使用默认 LLM provider（不再使用 profile）
        llm = LLMFactory.create_llm()

    subagents = get_all_subagents()

    # 获取所有工具
    tools = []
    tools.extend(get_k8s_tools())
    tools.extend(get_prometheus_tools())
    tools.extend(get_loki_tools())
    tools.extend(get_command_executor_tools())
    tools.extend(get_approval_tools())

    # 根据用户权限过滤工具
    if user_permissions is not None:
        original_count = len(tools)
        tools = filter_tools_by_permissions(tools, user_permissions)
        filtered_count = len(tools)
        logger.info(
            f"🔐 根据用户权限过滤工具: {original_count} → {filtered_count} "
            f"(权限: {', '.join(sorted(user_permissions))})"
        )
    else:
        logger.info(f"✅ 未指定用户权限，加载所有工具: {len(tools)} 个")

    # 配置中间件
    middleware = [MessageTrimmingMiddleware(max_messages=20), LoggingMiddleware()]
    logger.info("✅ 消息截断中间件已启用（保留最近 20 条消息，智能截断）")
    logger.info("✅ 日志中间件已启用")

    interrupt_on = _HIGH_RISK_TOOLS if enable_approval else None

    checkpointer = await get_checkpointer()

    agent = create_deep_agent(
        model=llm,
        system_prompt=MAIN_AGENT_SYSTEM_PROMPT,
        tools=tools,
        subagents=subagents,
        middleware=middleware,
        checkpointer=checkpointer,
        interrupt_on=interrupt_on,
    )

    # 只有在没有指定用户权限时才缓存 agent（全局默认 agent）
    if user_permissions is None:
        _agent = agent

    return agent


def get_thread_config(session_id: str) -> dict:
    """
    获取会话配置（用于 astream/ainvoke 的 config 参数）

    Args:
        session_id: 会话 ID

    Returns:
        LangGraph config dict，thread_id = session_id，与 chat_sessions 表关联
    """
    return {"configurable": {"thread_id": session_id}}
