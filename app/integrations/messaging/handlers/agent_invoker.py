"""
Agent 调用器 - 使用统一的 AgentChatService

职责：
- 调用统一的 AgentChatService 处理飞书消息
- 发送 AI 回复（卡片格式）
- 处理审批流程
"""

import asyncio
from typing import List, Dict, Any, Optional

from app.utils.logger import get_logger
from app.core.config import get_settings
from app.integrations.messaging.base_channel import ChannelContext, MessageType, OutgoingMessage
from app.integrations.feishu.message import build_formatted_reply_card
from app.integrations.feishu.message_formatter import clean_xml_tags, format_approval_request
from app.models.database import SessionLocal
from app.services.chat_service import save_feishu_message
from app.models.chat_message import MessageRole

# 导入统一的消息处理服务
from app.services.agent_chat_service import (
    AgentChatService,
    ChatRequest,
    MessageChannel,
    get_agent_chat_service
)

logger = get_logger(__name__)

# 全局会话锁字典（用于并发控制）
_session_locks: Dict[str, asyncio.Lock] = {}
_locks_lock = asyncio.Lock()


async def _get_session_lock(session_id: str) -> asyncio.Lock:
    """获取会话锁（线程安全）"""
    async with _locks_lock:
        if session_id not in _session_locks:
            _session_locks[session_id] = asyncio.Lock()
        return _session_locks[session_id]


class AgentInvoker:
    """Agent 调用器 - 使用统一的 AgentChatService"""

    def __init__(self, channel_adapter):
        self.channel = channel_adapter
        self.settings = get_settings()
        self.service = get_agent_chat_service()

    async def invoke_agent(self, context: ChannelContext, text: str) -> List[str]:
        """调用 Agent 并返回回复列表"""
        logger.info(f"🤖 调用 Agent: session={context.session_id}, text={text[:50]}...")

        # 获取会话锁
        session_lock = await _get_session_lock(context.session_id)

        async with session_lock:
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
            if response.reply:
                await self._send_reply(context.chat_id, response.reply, context)
                self._save_to_db(context.session_id, MessageRole.ASSISTANT, response.reply)
                return [response.reply]

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
