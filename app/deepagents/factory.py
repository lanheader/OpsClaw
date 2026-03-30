"""
DeepAgents 工厂函数（兼容层）

注意：从 v4.0 开始，Agent 创建由 main_agent.create_base_agent() 负责。
此文件保留是为了向后兼容，实际上只是调用 main_agent.get_ops_agent()。
FinalReportEnrichedAgent 已合并到 main_agent.DynamicAgentWrapper。
"""

from typing import Any, Optional, Set
from langchain_core.language_models import BaseChatModel
from app.deepagents.main_agent import get_ops_agent
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def create_agent_for_session(
    session_id: str,
    llm: Optional[BaseChatModel] = None,
    enable_approval: bool = True,
    enable_security: bool = True,
    user_permissions: Optional[Set[str]] = None,
    user_id: Optional[int] = None,
):
    """
    为会话创建 Agent（兼容接口，异步）

    v4.0 变更：
    - 不再包装 FinalReportEnrichedAgent（已合并到 DynamicAgentWrapper）
    - 直接返回 get_ops_agent() 的结果（已包含 final_report 保证）

    Args:
        session_id: 会话 ID（保留参数，兼容调用方）
        llm: 语言模型实例
        enable_approval: 是否启用批准流程
        enable_security: 已废弃，保留参数是为了兼容调用方
        user_permissions: 用户权限代码集合
        user_id: 用户 ID

    Returns:
        DynamicAgentWrapper 包装的 Agent 实例
    """
    logger.info(f"🔍 factory.create_agent_for_session: enable_approval={enable_approval}, user_id={user_id}")
    return await get_ops_agent(
        llm=llm,
        enable_approval=enable_approval,
        user_permissions=user_permissions,
        user_id=user_id,
    )


__all__ = ["create_agent_for_session"]
