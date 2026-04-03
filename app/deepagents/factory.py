"""
DeepAgents 工厂函数
"""

from typing import Optional, Set
from app.deepagents.main_agent import get_ops_agent
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def create_agent_for_session(  # type: ignore[no-untyped-def]
    enable_approval: bool = True,
    user_permissions: Optional[Set[str]] = None,
    user_id: Optional[int] = None,
):
    """
    为会话创建 Agent（兼容接口，异步）

    v4.0 变更：
    - 不再包装 FinalReportEnrichedAgent（已合并到 DynamicAgentWrapper）
    - 直接返回 get_ops_agent() 的结果（已包含 final_report 保证）

    Args:
        enable_approval: 是否启用批准流程
        user_permissions: 用户权限代码集合
        user_id: 用户 ID

    Returns:
        DynamicAgentWrapper 包装的 Agent 实例
    """
    logger.info(f"🔍 factory.create_agent_for_session: enable_approval={enable_approval}, user_id={user_id}")
    return await get_ops_agent(
        user_permissions=user_permissions,
        user_id=user_id,
        db=None,  # db 在 get_ops_agent 内部按需创建
    )


__all__ = ["create_agent_for_session"]
