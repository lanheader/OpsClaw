"""
审批流程处理器

职责：
- 检查是否有待审批操作
- 意图识别（同意/拒绝/澄清）
- 恢复工作流
"""

from typing import Optional, Dict, Any
from app.utils.logger import get_logger
from app.services.session_state_manager import SessionStateManager
from app.core.llm_factory import LLMFactory
from app.services.approval_intent_service import (
    classify_approval_intent,
    is_approval_keyword,
    is_rejection_keyword,
)
from app.integrations.feishu.approval_helpers import handle_approval_response
from app.integrations.feishu.message_formatter import (
    format_clarification_request,
    format_insufficient_confidence,
    format_pending_approval_warning,
    format_error_message,
    format_approval_confirmed,
    clean_xml_tags,
)
from app.integrations.feishu.message import build_formatted_reply_card

from app.integrations.messaging.base_channel import ChannelContext, MessageType, OutgoingMessage

logger = get_logger(__name__)


class ApprovalHandler:
    """审批流程处理器"""

    def __init__(self, channel_adapter):  # type: ignore[no-untyped-def]
        """
        初始化审批处理器

        Args:
            channel_adapter: 渠道适配器
        """
        self.channel = channel_adapter

    async def _send_card_message(self, chat_id: str, content: str) -> None:
        """发送卡片消息（支持 Markdown 渲染）"""
        cleaned = clean_xml_tags(content)
        card = build_formatted_reply_card(content=cleaned)
        outgoing = OutgoingMessage(
            chat_id=chat_id,
            message_type=MessageType.CARD,
            content=card,
        )
        await self.channel.send_message(outgoing)

    async def handle_pending_approval(
        self,
        context: ChannelContext,
        text: str
    ) -> bool:
        """
        处理待审批状态

        Args:
            context: 渠道上下文
            text: 用户输入

        Returns:
            True: 已处理审批
            False: 无待审批状态
        """
        # 检查是否有待审批状态
        approval_data = SessionStateManager.check_awaiting_approval(context.session_id)  # type: ignore[arg-type]
        if not approval_data:
            return False

        logger.info(f"✅ 检测到会话 {context.session_id} 处于等待批准状态")
        logger.info(f"📋 批准数据: {approval_data}")

        try:
            # 先尝试快速关键词匹配（无需 LLM，作为备选方案）
            if is_approval_keyword(text):
                logger.info(f"🚀 快速匹配: 检测到批准关键词")
                await self.resume_flow(context, "approved", text)
                return True

            if is_rejection_keyword(text):
                logger.info(f"🚀 快速匹配: 检测到拒绝关键词")
                await self.resume_flow(context, "rejected", text)
                return True

            # 使用 LLM 进行意图识别
            llm = LLMFactory.create_llm()
            intent_result = await classify_approval_intent(
                user_input=text,
                llm=llm,
                approval_context=approval_data,
            )

            intent_type = intent_result.get("intent_type")
            confidence = intent_result.get("confidence", 0)
            reasoning = intent_result.get("reasoning", "")

            logger.info(f"🎯 意图识别结果: {intent_type}, 置信度: {confidence}, 理由: {reasoning}")

            # 处理不同意图
            if intent_type == "approval" and confidence >= 0.7:
                await self.resume_flow(context, "approved", text)
                return True

            if intent_type == "rejection" and confidence >= 0.7:
                await self.resume_flow(context, "rejected", text)
                return True

            if intent_type == "clarification":
                logger.info("❓ 用户请求澄清")
                await self._send_clarification_message(context, approval_data)
                return True

            if confidence < 0.7:
                logger.warning(f"⚠️ 意图识别置信度不足: {confidence}")
                await self._send_insufficient_confidence_message(context, confidence, approval_data)
                return True

            # 用户提出了新请求，但当前有待批准的操作
            logger.info("🔄 用户提出了新请求，但当前有待批准的操作")
            await self._send_pending_approval_warning(context, approval_data)
            return True

        except Exception as exc:
            logger.error(f"❌ 处理批准响应失败: {exc}", exc_info=True)
            await self._send_error_message(context.chat_id, str(exc))

            # 重置会话状态
            SessionStateManager.reset_to_normal(context.session_id)  # type: ignore[arg-type]
            return True

    async def resume_flow(
        self,
        context: ChannelContext,
        decision: str,
        user_response: str
    ) -> None:
        """
        恢复工作流

        Args:
            context: 渠道上下文
            decision: 决策（approved/rejected）
            user_response: 用户响应
        """
        logger.info(f"{'✅' if decision == 'approved' else '❌'} 用户 {decision} 执行操作")

        try:
            # 先调用审批响应处理（它会检查 awaiting_approval 状态）
            resume_status = await handle_approval_response(
                session_id=context.session_id,  # type: ignore[arg-type]
                decision=decision,
                chat_id=context.chat_id,
                user_response=user_response,
                channel_adapter=self.channel
            )

            if resume_status == "completed":
                logger.info(f"✅ 工作流已恢复: decision={decision}")
                # 处理完成后清理会话状态
                SessionStateManager.reset_to_normal(context.session_id)  # type: ignore[arg-type]
            elif resume_status == "interrupted":
                # 有新的审批请求，这是正常状态，不需要清理会话状态
                logger.info(f"🔒 工作流恢复后有新的审批请求，等待用户审批")
                # 审批信息已经在 handle_approval_response 中保存
                # 发送确认消息
                from app.integrations.feishu.message_formatter import format_approval_confirmed, format_approval_request
                confirm_msg = format_approval_confirmed(decision)
                await self._send_card_message(context.chat_id, confirm_msg)

                # 🔥 重要：发送新的审批请求消息给用户
                # 从 SessionStateManager 获取新的审批信息
                new_approval_data = SessionStateManager.check_awaiting_approval(context.session_id)  # type: ignore[arg-type]
                if new_approval_data:
                    logger.info(f"📋 发送新的审批请求消息给用户")
                    # 从 HITLRequest 格式转换为显示格式
                    action_requests = new_approval_data.get('action_requests', [])
                    commands = []
                    for req in action_requests:
                        tool_name = req.get('name', 'unknown')
                        tool_args = req.get('args', {})
                        description = req.get('description', '')

                        # 从工具名推断类型
                        if tool_name.startswith('delete_') or tool_name.startswith('restart_') or tool_name.startswith('scale_'):
                            tool_type = 'k8s'
                        elif tool_name.startswith('query_') or tool_name.startswith('get_'):
                            if 'prometheus' in tool_name.lower() or 'cpu' in tool_name.lower() or 'memory' in tool_name.lower():
                                tool_type = 'prometheus'
                            elif 'log' in tool_name.lower():
                                tool_type = 'logs'
                            else:
                                tool_type = 'k8s'
                        else:
                            tool_type = 'k8s'

                        commands.append({
                            'type': tool_type,
                            'action': tool_name,
                            'params': tool_args,
                            'reason': description
                        })

                    # 从 review_configs 推断风险等级
                    review_configs = new_approval_data.get('review_configs', [])
                    risk_level = '中等风险'
                    if review_configs:
                        allowed_decisions = review_configs[0].get('allowed_decisions', [])
                        if 'reject' in allowed_decisions:
                            risk_level = '高风险操作'
                        elif 'edit' in allowed_decisions:
                            risk_level = '中等风险'

                    approval_msg = format_approval_request(
                        commands=commands,
                        risk_level=risk_level,
                        user_input=''
                    )
                    await self._send_card_message(context.chat_id, approval_msg)
                else:
                    logger.warning(f"⚠️ 无法获取新的审批信息，session_id={context.session_id}")
            elif resume_status == "not_awaiting":
                logger.warning(f"⚠️ 会话 {context.session_id} 不在等待批准状态")
            else:
                logger.error(f"❌ 恢复工作流失败: {resume_status}")

        except Exception as exc:
            logger.exception(f"❌ 恢复批准流程失败: {exc}")
            await self._send_error_message(context.chat_id, f"恢复工作流失败: {str(exc)}")

    async def _send_clarification_message(
        self,
        context: ChannelContext,
        approval_data: Dict[str, Any]
    ) -> None:
        """发送澄清请求消息"""
        clarification_msg = format_clarification_request(
            commands_summary=approval_data.get("commands_summary", "未知操作"),
            risk_level=approval_data.get("risk_level", "未知"),
        )
        await self._send_card_message(context.chat_id, clarification_msg)

    async def _send_insufficient_confidence_message(
        self,
        context: ChannelContext,
        confidence: float,
        approval_data: Dict[str, Any]
    ) -> None:
        """发送置信度不足消息"""
        msg = format_insufficient_confidence(confidence, approval_data)
        await self._send_card_message(context.chat_id, msg)

    async def _send_pending_approval_warning(
        self,
        context: ChannelContext,
        approval_data: Dict[str, Any]
    ) -> None:
        """发送待审批警告消息"""
        msg = format_pending_approval_warning(approval_data)
        await self._send_card_message(context.chat_id, msg)

    async def _send_error_message(self, chat_id: str, error_msg: str) -> None:
        """发送错误消息"""
        msg = format_error_message(error_msg)  # type: ignore[arg-type]
        try:
            await self._send_card_message(chat_id, msg)
        except Exception as e:
            logger.error(f"发送错误消息失败: {e}")
