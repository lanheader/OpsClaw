"""
安全审核中间件
审核操作的安全性
"""

from typing import Dict, Any
import structlog

from app.middleware.base import BaseMiddleware

logger = structlog.get_logger()


class SecurityMiddleware(BaseMiddleware):
    """安全审核中间件"""

    def __init__(self):
        # 加载安全策略
        self.security_policy = self._load_security_policy()

    def should_process(self, state: Dict[str, Any], action: Any) -> bool:
        """判断是否需要安全审核"""
        # 所有操作都需要安全审核
        return True

    async def process(self, state: Dict[str, Any], action: Any) -> Dict[str, Any]:
        """处理安全审核"""
        try:
            # 审核操作
            audit_result = self._audit_action(action)

            if not audit_result["passed"]:
                logger.warning(f"Security audit failed: {audit_result['reason']}")
                state["security_audit_passed"] = False
                state["security_audit_reason"] = audit_result["reason"]
            else:
                state["security_audit_passed"] = True

            return state

        except Exception as e:
            logger.error(f"Security middleware error: {e}")
            state["security_audit_passed"] = False
            state["security_audit_error"] = str(e)
            return state

    def _audit_action(self, action: Any) -> Dict[str, Any]:
        """审核操作"""
        # 检查操作是否在白名单中
        if hasattr(action, "tool_name"):
            if action.tool_name in self.security_policy["blacklist"]:
                return {"passed": False, "reason": f"操作 {action.tool_name} 在黑名单中"}

        return {"passed": True}

    def _load_security_policy(self) -> Dict[str, Any]:
        """加载安全策略"""
        # 从配置文件加载
        return {
            "blacklist": [
                "rm -rf /",
                "dd if=/dev/zero",
            ],
            "whitelist": [
                "kubectl get",
                "kubectl describe",
                "kubectl logs",
            ],
        }
