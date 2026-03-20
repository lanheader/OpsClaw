"""
批准流程中间件
处理用户批准流程,集成 ApprovalIntentService
"""

import asyncio
from typing import Dict, Any
import structlog

from app.middleware.base import BaseMiddleware
from app.services.approval_intent_service import classify_approval_intent
from app.integrations.feishu.client import FeishuClient
from app.core.llm_factory import LLMFactory

logger = structlog.get_logger()


class ApprovalMiddleware(BaseMiddleware):
    """批准流程中间件"""

    def __init__(self):
        try:
            self.feishu_client = FeishuClient()
        except TypeError:
            # FeishuClient 需要参数，暂时设为 None
            self.feishu_client = None
        self.llm = LLMFactory.create_llm()
        self.pending_approvals = {}  # 存储待批准的请求

    def should_process(self, state: Dict[str, Any], action: Any) -> bool:
        """判断是否需要批准"""
        # 检查操作是否需要批准
        if hasattr(action, "tool_name"):
            # 高风险操作需要批准
            high_risk_tools = [
                "delete_pod",
                "restart_deployment",
                "scale_deployment",
                "update_configmap",
                "execute_command",
            ]
            return action.tool_name in high_risk_tools

        return False

    async def process(self, state: Dict[str, Any], action: Any) -> Dict[str, Any]:
        """处理批准流程"""
        try:
            # 1. 发送批准请求到飞书
            approval_data = self._prepare_approval_data(action)
            message_id = await self._send_approval_request(approval_data)

            # 2. 存储待批准请求
            self.pending_approvals[message_id] = {
                "action": action,
                "state": state,
                "status": "pending",
            }

            # 3. 等待用户回复
            approval_result = await self._wait_for_approval(message_id)

            # 4. 处理批准结果
            if approval_result["approved"]:
                logger.info(f"Action approved: {action.tool_name}")
                state["approval_status"] = "approved"
            else:
                logger.info(f"Action rejected: {action.tool_name}")
                state["approval_status"] = "rejected"
                state["rejection_reason"] = approval_result.get("reason", "用户拒绝")

            return state

        except Exception as e:
            logger.error(f"Approval middleware error: {e}")
            state["approval_status"] = "error"
            state["error"] = str(e)
            return state

    async def _send_approval_request(self, approval_data: Dict[str, Any]) -> str:
        """发送批准请求到飞书"""
        message = self._format_approval_message(approval_data)
        message_id = await self.feishu_client.send_interactive_message(message)
        return message_id

    async def _wait_for_approval(self, message_id: str, timeout: int = 300) -> Dict[str, Any]:
        """
        等待用户批准

        Args:
            message_id: 消息 ID
            timeout: 超时时间 (秒)

        Returns:
            批准结果
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            # 检查是否超时
            if asyncio.get_event_loop().time() - start_time > timeout:
                return {"approved": False, "reason": "超时未响应"}

            # 检查是否有用户回复
            approval = self.pending_approvals.get(message_id)
            if approval and approval["status"] != "pending":
                return {
                    "approved": approval["status"] == "approved",
                    "reason": approval.get("reason", ""),
                }

            # 等待 1 秒后重试
            await asyncio.sleep(1)

    async def handle_user_reply(self, message_id: str, user_input: str) -> None:
        """
        处理用户回复

        Args:
            message_id: 消息 ID
            user_input: 用户输入
        """
        # 使用 ApprovalIntentService 识别意图
        approval = self.pending_approvals.get(message_id)
        if not approval:
            logger.warning(f"No pending approval found for message {message_id}")
            return

        # 识别用户意图
        intent_result = await classify_approval_intent(
            user_input=user_input, llm=self.llm, approval_context=approval
        )

        intent_type = intent_result.get("intent_type")
        confidence = intent_result.get("confidence", 0)

        # 根据意图类型处理
        if intent_type == "approval" and confidence >= 0.7:
            # 用户批准
            approval["status"] = "approved"
            logger.info(f"User approved action for message {message_id}")
        elif intent_type == "rejection" and confidence >= 0.7:
            # 用户拒绝
            approval["status"] = "rejected"
            approval["reason"] = intent_result.get("reasoning", "用户拒绝")
            logger.info(f"User rejected action for message {message_id}")
        elif intent_type == "clarification":
            # 用户请求澄清
            clarification_msg = self._generate_clarification(approval)
            await self.feishu_client.send_text_message(clarification_msg)
        else:
            # 无法识别意图
            await self.feishu_client.send_text_message(
                "抱歉,我无法理解您的回复。请回复 '批准' 或 '拒绝'。"
            )

    def _prepare_approval_data(self, action: Any) -> Dict[str, Any]:
        """准备批准数据"""
        return {
            "tool_name": action.tool_name,
            "tool_args": action.tool_args,
            "risk": self._assess_risk(action),
            "description": self._generate_description(action),
        }

    def _assess_risk(self, action: Any) -> str:
        """评估操作风险"""
        # 根据操作类型评估风险
        high_risk_tools = ["delete_pod", "execute_command"]
        if action.tool_name in high_risk_tools:
            return "high"
        return "medium"

    def _generate_description(self, action: Any) -> str:
        """生成操作描述"""
        # 根据操作类型生成描述
        descriptions = {
            "delete_pod": "删除 Pod",
            "restart_deployment": "重启 Deployment",
            "scale_deployment": "扩缩容 Deployment",
        }
        return descriptions.get(action.tool_name, "执行操作")

    def _format_approval_message(self, approval_data: Dict[str, Any]) -> Dict:
        """格式化批准消息"""
        return {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"content": "🚨 需要您的批准", "tag": "plain_text"}},
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "content": f"**操作类型**: {approval_data['description']}",
                            "tag": "lark_md",
                        },
                    },
                    {
                        "tag": "div",
                        "text": {
                            "content": f"**风险评估**: {approval_data['risk']}",
                            "tag": "lark_md",
                        },
                    },
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {"content": "批准", "tag": "plain_text"},
                                "type": "primary",
                                "value": {"action": "approve"},
                            },
                            {
                                "tag": "button",
                                "text": {"content": "拒绝", "tag": "plain_text"},
                                "type": "danger",
                                "value": {"action": "reject"},
                            },
                        ],
                    },
                ],
            },
        }

    def _generate_clarification(self, approval: Dict[str, Any]) -> str:
        """生成澄清消息"""
        action = approval["action"]
        return f"""
关于这个操作的详细信息:

**操作**: {action.tool_name}
**参数**: {action.tool_args}
**风险**: {self._assess_risk(action)}

这个操作将会 {self._generate_description(action)}。

请问您是否批准这个操作?
"""
