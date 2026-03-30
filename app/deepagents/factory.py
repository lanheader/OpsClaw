"""
DeepAgents 工厂函数（兼容层）

注意：从 v3.0 开始，会话管理由 LangGraph checkpointer 自动处理。
此文件保留是为了向后兼容，实际上只是调用 main_agent.get_ops_agent()。
"""

from typing import Any, Optional, Set
from langchain_core.language_models import BaseChatModel
from app.deepagents.main_agent import get_ops_agent
from app.utils.llm_helper import ensure_final_report_in_state
from app.utils.logger import get_logger

logger = get_logger(__name__)


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
        """
        流式处理，确保最后一个事件包含 final_report

        LangGraph astream 返回格式: {node_name: state}
        最后一个节点事件通常包含完整的最终状态
        """
        last_event = None
        last_node_name = None
        event_count = 0

        async for event in self._agent.astream(input_data, config=config, **kwargs):
            event_count += 1

            # 处理自定义 complete 事件（如果存在）
            if (
                isinstance(event, dict)
                and event.get("type") == "complete"
                and isinstance(event.get("state"), dict)
            ):
                yield {
                    **event,
                    "state": ensure_final_report_in_state(event["state"]),
                }
                last_event = None  # 已经处理过了
                continue

            # 处理 __interrupt__ 事件（审批中断）
            if isinstance(event, dict) and "__interrupt__" in event:
                yield event
                last_event = None  # 中断不需要后续处理
                continue

            # 记录最后一个节点事件
            if isinstance(event, dict):
                # 提取节点名（跳过内部字段）
                for key in event.keys():
                    if not key.startswith("__"):
                        last_event = event
                        last_node_name = key
                        break

            yield event

        # 流结束后，如果最后一个事件是节点事件，确保包含 final_report
        if last_event and last_node_name:
            node_state = last_event.get(last_node_name, {})
            if isinstance(node_state, dict) and "messages" in node_state:
                # 尝试确保 final_report 存在
                enriched_state = ensure_final_report_in_state(node_state)

                # 如果生成了 final_report，发送一个 complete 事件
                if enriched_state.get("formatted_response") or enriched_state.get("final_report"):
                    logger.info(f"📝 流结束后生成 final_report (长度: {len(enriched_state.get('formatted_response', '') or enriched_state.get('final_report', ''))})")
                    yield {
                        "type": "complete",
                        "state": enriched_state,
                        "node": last_node_name,
                    }

    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)


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

    注意：从 v3.0 开始，所有会话共享同一个编译图，
    通过 checkpointer + thread_id 区分会话状态。

    Args:
        session_id: 会话 ID（实际上不再需要，保留是为了兼容）
        llm: 语言模型实例
        enable_approval: 是否启用批准流程
        enable_security: 已废弃，保留参数是为了兼容调用方，不再生效
        user_permissions: 用户权限代码集合，用于过滤可用工具
        user_id: 用户 ID（用于动态获取审批配置）

    Returns:
        Agent 实例（单例）
    """
    # 直接返回单例 agent
    # session_id 不再用于创建不同的 agent，而是在调用时通过 config 传递
    logger.info(f"🔍 factory.create_agent_for_session: enable_approval={enable_approval}, user_id={user_id}")
    agent = await get_ops_agent(
        llm=llm,
        enable_approval=enable_approval,
        user_permissions=user_permissions,
        user_id=user_id,
    )
    return FinalReportEnrichedAgent(agent)
