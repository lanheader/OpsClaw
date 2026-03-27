"""
DeepAgents 工厂函数（兼容层）

注意：从 v3.0 开始，会话管理由 LangGraph checkpointer 自动处理。
此文件保留是为了向后兼容，实际上只是调用 main_agent.get_ops_agent()。
"""

from typing import Any, Optional, Set
from langchain_core.language_models import BaseChatModel
from app.deepagents.main_agent import get_ops_agent
from app.utils.llm_helper import ensure_final_report_in_state


class FinalReportEnrichedAgent:
    """为 DeepAgent 结果补齐 final_report，避免上层拿到空最终回复。"""

    def __init__(self, agent: Any):
        self._agent = agent

    async def ainvoke(self, input_data: Any, config: Optional[dict] = None, **kwargs: Any) -> Any:
        result = await self._agent.ainvoke(input_data, config=config, **kwargs)
        if isinstance(result, dict):
            return ensure_final_report_in_state(result)
        return result

    async def astream(self, input_data: Any, config: Optional[dict] = None, **kwargs: Any):
        async for event in self._agent.astream(input_data, config=config, **kwargs):
            if (
                isinstance(event, dict)
                and event.get("type") == "complete"  # 修复：使用 "type" 而不是 "event"
                and isinstance(event.get("state"), dict)
            ):
                yield {
                    **event,
                    "state": ensure_final_report_in_state(event["state"]),
                }
                continue

            yield event

    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)


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
    agent = await get_ops_agent(
        llm=llm,
        enable_approval=enable_approval,
        user_permissions=user_permissions,
    )
    return FinalReportEnrichedAgent(agent)
