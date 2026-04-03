"""
飞书回调处理（适配器层）

此文件保留作为向后兼容的适配器，内部调用新架构的消息处理。
所有实际处理逻辑已迁移到新架构：
- app/integrations/messaging/ (新架构)
- app/integrations/messaging/adapters/feishu_adapter.py (飞书适配器)
- app/integrations/messaging/message_processor.py (消息处理器)
"""

import asyncio
import gzip
import base64
import hashlib
import json
from typing import Dict, Any, Literal
from Crypto.Cipher import AES

from app.utils.logger import get_logger
from app.integrations.messaging.registry import get_channel_adapter
from app.integrations.messaging.base_channel import IncomingMessage
from app.integrations.messaging.message_processor import MessageProcessor
from app.integrations.feishu.approval_helpers import handle_approval_response
from app.core.config import get_settings

logger = get_logger(__name__)

def _is_bot_mentioned(message: Dict[str, Any], bot_id: str) -> bool:
    """
    检查消息是否 @ 了机器人

    Args:
        message: 飞书消息对象
        bot_id: 机器人的 app_id 或 open_id

    Returns:
        是否 @ 了机器人
    """
    try:
        mentions = message.get("mentions", [])
        for mention in mentions:
            mention_id = mention.get("id", {})
            # 检查 open_id 或 app_id
            if mention_id.get("open_id") == bot_id or mention_id.get("app_id") == bot_id:
                return True
        return False
    except Exception as e:
        logger.warning(f"检查 @机器人 失败: {e}")
        return False

async def handle_message_receive(message: Dict[str, Any]) -> None:
    """
    处理飞书消息接收（重定向到新架构）

    此函数保留用于向后兼容，内部调用新架构的 MessageProcessor。
    """
    try:
        settings = get_settings()

        # Webhook 模式下检查是否需要 @机器人
        if (settings.FEISHU_CONNECTION_MODE == "webhook" and
            settings.FEISHU_WEBHOOK_REQUIRE_MENTION):

            bot_id = settings.FEISHU_APP_ID
            if not _is_bot_mentioned(message, bot_id):  # type: ignore[arg-type]
                logger.info("⏭️  消息未 @ 机器人，跳过处理")
                return

        # 获取飞书适配器
        adapter = get_channel_adapter("feishu")

        if not adapter:
            logger.error("❌ 飞书适配器未初始化")
            return

        # 解析消息为新架构格式
        message = IncomingMessage(  # type: ignore[assignment]
            channel_type="feishu",
            channel_id="feishu_main",
            message_id=message.get("message_id", ""),
            message_type="text",  # type: ignore[arg-type]
            action_type="receive",  # type: ignore[arg-type]
            sender_id=_extract_sender_id(message),
            sender_name=None,  # 后续获取
            chat_id=message.get("chat_id", ""),
            raw_content=message,
            raw_headers={},
            text=_extract_message_text(message),
        )

        # 使用新架构处理消息
        processor = MessageProcessor(adapter)
        await processor.process_message(message)  # type: ignore[arg-type]

    except Exception as e:
        logger.exception(f"❌ 处理飞书消息失败: {e}")


async def handle_card_action(action: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理飞书卡片动作（重定向到新架构）

    此函数保留用于向后兼容。
    """
    logger.info(f"📝 收到卡片动作: {action.get('action', {})}")

    # 卡片动作通常与审批相关，使用新架构的审批处理器
    # TODO: 实现完整的卡片动作处理

    return {
        "code": 0,
        "msg": "success"
    }


async def send_approval_response(
    session_id: str,
    decision: str,
    chat_id: str,
    user_response: str,
) -> Dict[str, Any]:
    """
    发送批准响应（重定向到新架构）

    此函数保留用于向后兼容。
    """
    adapter = get_channel_adapter("feishu")

    status = await handle_approval_response(
        session_id=session_id,
        decision=decision,
        chat_id=chat_id,
        user_response=user_response,
        channel_adapter=adapter
    )

    return {
        "code": 0 if status == "completed" else 1,
        "msg": status
    }


# ========== 辅助函数 ==========

def _extract_sender_id(message: Dict[str, Any]) -> str:
    """从消息中提取发送者 ID"""
    try:
        sender = message.get("sender", {})
        sender_id = sender.get("sender_id", {}).get("user_id", "")
        return sender_id  # type: ignore[no-any-return]
    except Exception:
        return ""


def _extract_message_text(message: Dict[str, Any]) -> str:
    """从消息中提取文本内容"""
    try:
        raw_content = message.get("content", {})

        # content 可能是 JSON 字符串（来自 lark_longconn），需要先解析
        if isinstance(raw_content, str):
            try:
                raw_content = json.loads(raw_content)
            except (json.JSONDecodeError, ValueError):
                return raw_content  # 纯文本直接返回  # type: ignore[no-any-return]

        # 文本消息
        if "text" in raw_content:
            return raw_content.get("text", "")  # type: ignore[no-any-return]

        # 富文本消息
        if "rich_text" in raw_content:
            elements = raw_content.get("rich_text", {}).get("elements", [])
            texts = []
            for elem in elements:
                if elem.get("type") == "text":
                    text_run = elem.get("text_run", {})
                    texts.append(text_run.get("content", ""))
            return "".join(texts)

        return ""
    except Exception:
        return ""


async def decrypt_message(encrypt_key: str, encrypted_data: str) -> str:
    """
    解密飞书消息（保留用于兼容）

    注意：新架构使用 FeishuChannelAdapter.decrypt_message()
    """
    try:
        # Base64 解码
        encrypted_bytes = base64.b64decode(encrypted_data)

        # AES 解密
        cipher = AES.new(
            encrypt_key.encode("utf-8")[:16].encode("utf-8"),  # type: ignore[attr-defined]
            AES.MODE_ECB
        )
        decrypted_bytes = cipher.decrypt(encrypted_bytes)

        # 去除 padding
        padding = decrypted_bytes[-1]
        if isinstance(padding, str):
            padding = ord(padding)
        decrypted_bytes = decrypted_bytes[:-padding]

        # Gzip 解压
        decrypted_str = gzip.decompress(decrypted_bytes).decode("utf-8")

        return decrypted_str

    except Exception as e:
        logger.error(f"❌ 解密消息失败: {e}")
        raise


async def verify_webhook_signature(
    timestamp: str,
    nonce: str,
    encrypt_key: str,
    body: str,
    signature: str
) -> bool:
    """
    验证飞书 Webhook 签名（保留用于兼容）

    注意：新架构使用 FeishuChannelAdapter.verify_request()
    """
    try:
        # 构造签名串
        sign_str = f"{timestamp}{nonce}{encrypt_key}{body}"
        sign_bytes = sign_str.encode("utf-8")

        # 计算 MD5
        calculated_signature = hashlib.md5(sign_bytes).hexdigest()

        return calculated_signature == signature

    except Exception as e:
        logger.error(f"❌ 签名验证失败: {e}")
        return False

__all__ = [
    "handle_message_receive",
    "handle_card_action",
    "send_approval_response",
    "decrypt_message",
    "verify_webhook_signature",
]
