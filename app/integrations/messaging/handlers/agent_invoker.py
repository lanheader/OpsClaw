"""
Agent 调用器 - 使用统一的 AgentChatService

职责：
- 调用统一的 AgentChatService 处理飞书消息
- 发送 AI 回复（卡片格式）
- 处理审批流程
- 使用统一的会话锁管理器
- 回复质量检查（外部后处理）
"""

import asyncio
import re
from typing import List, Dict, Any, Optional

from app.utils.logger import get_logger
from app.core.config import get_settings
from app.integrations.messaging.base_channel import ChannelContext, MessageType, OutgoingMessage
from app.integrations.feishu.message import build_formatted_reply_card
from app.integrations.feishu.message_formatter import clean_xml_tags, format_approval_request
from app.models.database import SessionLocal
from app.services.chat_service import save_feishu_message
from app.models.chat_message import MessageRole
from app.services.session_lock_manager import SessionLockContext

# 导入统一的消息处理服务
from app.services.agent_chat_service import (
    AgentChatService,
    ChatRequest,
    MessageChannel,
    get_agent_chat_service
)

logger = get_logger(__name__)

# 质量检查：低质量回复关键词
_LOW_QUALITY_PATTERNS = [
    re.compile(r'任务已完成，但没有生成文本回复'),
    re.compile(r'没有生成文本回复'),
    re.compile(r'^任务已完成\s*$'),
    re.compile(r'^操作已完成\s*$'),
]

# 最大重试次数
_MAX_QUALITY_RETRIES = 1


class AgentInvoker:
    """Agent 调用器 - 使用统一的 AgentChatService"""

    def __init__(self, channel_adapter):
        self.channel = channel_adapter
        self.settings = get_settings()
        self.service = get_agent_chat_service()

    async def invoke_agent(self, context: ChannelContext, text: str) -> List[str]:
        """调用 Agent 并返回回复列表"""
        logger.info(f"🤖 调用 Agent: session={context.session_id}, text={text[:50]}...")

        # 使用统一的会话锁管理器
        async with SessionLockContext(context.session_id, timeout=600):
            logger.info(f"🔒 获取会话锁: session={context.session_id}")

            # 构建请求
            request = ChatRequest(
                session_id=context.session_id,
                user_id=context.user_id,
                content=text,
                channel=MessageChannel.FEISHU,
                user_permissions=list(context.user_permissions or []),
                chat_id=context.chat_id,
                enable_security=True,
            )

            # 使用统一服务处理
            response = await self.service.process_message(request)

            # 处理审批请求
            if response.needs_approval and response.approval_data:
                await self._handle_approval_request(context, response.approval_data)
                return []

            # 处理正常回复
            reply = response.reply
            if reply:
                # 质量检查 + 重试
                for attempt in range(_MAX_QUALITY_RETRIES + 1):
                    quality_result = self._check_reply_quality(reply, text)
                    if quality_result.is_good:
                        break

                    logger.warning(
                        f"🔍 [质量检查] 回复质量不达标 (第{attempt + 1}次): {quality_result.reason}"
                    )
                    if attempt >= _MAX_QUALITY_RETRIES:
                        logger.warning("🔍 [质量检查] 达到最大重试次数，使用原回复")
                        break

                    # 用质量反馈重新请求
                    feedback = quality_result.feedback
                    logger.info(f"🔍 [质量检查] 发送质量反馈重新请求: {feedback[:100]}...")
                    retry_request = ChatRequest(
                        session_id=context.session_id,
                        user_id=context.user_id,
                        content=feedback,
                        channel=MessageChannel.FEISHU,
                        user_permissions=list(context.user_permissions or []),
                        chat_id=context.chat_id,
                        enable_security=True,
                    )
                    retry_response = await self.service.process_message(retry_request)
                    if retry_response.reply and not self._check_reply_quality(retry_response.reply, text).is_good == False:
                        reply = retry_response.reply
                    elif retry_response.reply:
                        reply = retry_response.reply

                await self._send_reply(context.chat_id, reply, context)
                self._save_to_db(context.session_id, MessageRole.ASSISTANT, reply)
                return [reply]

            # 空回复兜底
            fallback = (
                "⚠️ 本次未能生成回复，可能原因：\n"
                "- 对话上下文过长，模型处理超限\n"
                "- 模型暂时无响应\n\n"
                "建议：发送 /new 开启新会话后重试。"
            )
            await self._send_reply(context.chat_id, fallback, context)
            self._save_to_db(context.session_id, MessageRole.ASSISTANT, fallback)
            return [fallback]

    async def _handle_approval_request(
        self,
        context: ChannelContext,
        approval_data: Dict[str, Any]
    ) -> None:
        """处理审批请求"""
        logger.info(f"📋 处理审批请求: session={context.session_id}")

        approval_message = approval_data.get("message", "")
        commands = approval_data.get("commands", [])

        # 格式化审批请求消息
        approval_msg = format_approval_request(
            commands=commands,
            risk_level="中等风险",
            user_input=""
        )

        # 发送审批请求卡片
        cleaned_approval = clean_xml_tags(approval_msg)

        # 获取用户 ID（用于 @）
        mention_user_id = None
        if self.settings.FEISHU_REPLY_WITH_MENTION and context:
            mention_user_id = context.sender_id
            logger.info(f"🔔 启用 @用户回复: user_id={mention_user_id}")

        card = build_formatted_reply_card(
            content=cleaned_approval,
            mention_user_id=mention_user_id
        )

        outgoing = OutgoingMessage(
            chat_id=context.chat_id,
            message_type=MessageType.CARD,
            content=card
        )
        await self.channel.send_message(outgoing)

        # 保存审批请求到数据库
        self._save_to_db(
            context.session_id,
            MessageRole.ASSISTANT,
            f"## 📋 命令规划\n\n{approval_message}\n\n"
        )

        logger.info("✅ 审批请求已发送，等待用户响应")

    async def _send_reply(
        self,
        chat_id: str,
        content: str,
        context: Optional[ChannelContext] = None
    ) -> None:
        """发送回复消息（卡片格式）"""
        logger.info(f"🔍 [卡片转换] 原始内容: {content[:200]}...")

        cleaned = clean_xml_tags(content)
        logger.info(f"🔍 [卡片转换] 清理后内容: {cleaned[:200]}...")

        # 获取用户 ID（用于 @）
        mention_user_id = None
        if self.settings.FEISHU_REPLY_WITH_MENTION and context:
            mention_user_id = context.sender_id
            logger.info(f"🔔 启用 @用户回复: user_id={mention_user_id}")

        card = build_formatted_reply_card(
            content=cleaned,
            mention_user_id=mention_user_id
        )

        outgoing = OutgoingMessage(
            chat_id=chat_id,
            message_type=MessageType.CARD,
            content=card,
        )
        await self.channel.send_message(outgoing)

    def _save_to_db(
        self,
        session_id: Optional[str],
        role: MessageRole,
        content: str
    ) -> None:
        """保存消息到数据库"""
        if not session_id:
            return

        db = SessionLocal()
        try:
            save_feishu_message(db, session_id, role, content)
            logger.info(f"✅ 已保存消息到数据库: session={session_id}, role={role.value}")
        except Exception as e:
            logger.error(f"❌ 保存消息到数据库失败: {e}")
        finally:
            db.close()

    def _check_reply_quality(self, reply: str, user_query: str) -> "QualityResult":
        """
        检查回复质量（本地规则，不调 LLM，零延迟零成本）

        检查项：
        1. 是否命中已知低质量模板
        2. 回复长度是否过短
        3. 回复是否包含实质信息（数据、结论、建议）
        """
        reasons = []
        feedback_parts = []

        # 1. 低质量模板匹配
        for pattern in _LOW_QUALITY_PATTERNS:
            if pattern.search(reply):
                reasons.append("命中低质量模板")
                feedback_parts.append(
                    f"你的回复 '{reply[:50]}' 属于低质量回复。"
                    f"请根据用户的问题「{user_query[:100]}」和之前工具调用获取的数据，"
                    f"直接给出具体的分析结论和数据。不要只说任务完成。"
                )
                break

        # 2. 回复过短（< 20 字符）且没有实质内容
        if len(reply.strip()) < 20:
            reasons.append(f"回复过短（{len(reply.strip())}字符）")
            feedback_parts.append(
                f"你的回复太短了（'{reply}'），无法有效回答用户问题。"
                f"请提供更详细的分析和结论。"
            )

        # 3. 只有工具报错没有分析
        if self._is_only_errors(reply):
            reasons.append("只有错误信息没有分析")
            feedback_parts.append(
                f"你的回复只包含了工具错误信息，没有给出有用的分析和建议。"
                f"请根据已有信息分析问题原因，并告诉用户下一步应该怎么做。"
            )

        if reasons:
            return QualityResult(
                is_good=False,
                reason="; ".join(reasons),
                feedback="\n\n".join(feedback_parts)
            )

        return QualityResult(is_good=True, reason="", feedback="")

    @staticmethod
    def _is_only_errors(reply: str) -> bool:
        """检查回复是否只包含错误信息"""
        error_keywords = ["操作失败", "error", "Error", "失败", "执行失败", "工具调用失败"]
        lines = [l.strip() for l in reply.strip().split("\n") if l.strip()]
        if len(lines) == 0:
            return False
        # 超过 70% 的非空行包含错误关键词
        error_line_count = sum(
            1 for l in lines if any(kw in l for kw in error_keywords)
        )
        return len(lines) >= 2 and error_line_count / len(lines) > 0.7


class QualityResult:
    """质量检查结果"""
    def __init__(self, is_good: bool, reason: str, feedback: str):
        self.is_good = is_good
        self.reason = reason
        self.feedback = feedback
