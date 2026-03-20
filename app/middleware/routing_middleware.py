"""
智能路由中间件
替代 IntelligentRouterAgent,提供智能路由决策
"""

from typing import Dict, Any
import structlog

from app.middleware.base import BaseMiddleware

logger = structlog.get_logger()


class RoutingMiddleware(BaseMiddleware):
    """智能路由中间件"""

    def should_process(self, state: Dict[str, Any], action: Any) -> bool:
        """判断是否需要路由"""
        # 在特定节点需要路由决策
        return state.get("needs_routing", False)

    async def process(self, state: Dict[str, Any], action: Any) -> Dict[str, Any]:
        """处理路由逻辑"""
        try:
            # 根据状态决定下一步
            next_step = self._decide_next_step(state)
            state["next_step"] = next_step
            logger.info(f"Routing decision: {next_step}")
            return state

        except Exception as e:
            logger.error(f"Routing middleware error: {e}")
            state["routing_error"] = str(e)
            return state

    def _decide_next_step(self, state: Dict[str, Any]) -> str:
        """决定下一步"""
        # 根据意图类型路由
        intent = state.get("intent_type")

        if intent == "query":
            return "data_collection"
        elif intent == "diagnose":
            return "diagnosis"
        elif intent == "operate":
            return "execution"
        else:
            return "clarification"
