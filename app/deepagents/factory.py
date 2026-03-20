"""
DeepAgents 工厂函数（兼容层）

注意：从 v3.0 开始，会话管理由 LangGraph checkpointer 自动处理。
此文件保留是为了向后兼容，实际上只是调用 main_agent.get_ops_agent()。
"""

from typing import Optional, Set
from langchain_core.language_models import BaseChatModel
from app.deepagents.main_agent import get_ops_agent


async def create_agent_for_session(
    session_id: str,
    llm: Optional[BaseChatModel] = None,
    enable_approval: bool = True,
    enable_security: bool = True,
    user_permissions: Optional[Set[str]] = None,
):
    """
    为会话创建 Agent（兼容接口，异步）

    注意：从 v3.0 开始，所有会话共享同一个编译图，
    通过 checkpointer + thread_id 区分会话状态。

    Args:
        session_id: 会话 ID（实际上不再需要，保留是为了兼容）
        llm: 语言模型实例
        enable_approval: 是否启用批准流程
        enable_security: 已废弃，保留参数是为了兼容调用方，不再生效
        user_permissions: 用户权限代码集合，用于过滤可用工具

    Returns:
        Agent 实例（单例）
    """
    # 直接返回单例 agent
    # session_id 不再用于创建不同的 agent，而是在调用时通过 config 传递
    return await get_ops_agent(
        llm=llm,
        enable_approval=enable_approval,
        user_permissions=user_permissions,
    )
