# app/api/v1/feishu.py
"""飞书集成 API 端点"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Header

from app.core.config import get_settings
from app.integrations.feishu.callback import (
    verify_webhook_signature,
    decrypt_message,
    handle_card_action,
    handle_message_receive,
    send_approval_response,
)
from app.integrations.feishu.client import get_feishu_client
from app.integrations.feishu.lark_longconn import get_feishu_longconn_client
from app.integrations.feishu.message import send_notification

router = APIRouter(prefix="/feishu", tags=["feishu"])
logger = logging.getLogger(__name__)


@router.post("/callback")
async def feishu_callback(
    request: Request,
    x_lark_request_timestamp: Optional[str] = Header(None),
    x_lark_request_nonce: Optional[str] = Header(None),
    x_lark_signature: Optional[str] = Header(None),
):
    """
    飞书事件回调端点。

    接收飞书的事件推送：
    - URL 验证（challenge）
    - 消息事件
    - 卡片交互事件

    参数：
        request: FastAPI 请求对象
        x_lark_request_timestamp: 请求时间戳（Header）
        x_lark_request_nonce: 随机数（Header）
        x_lark_signature: 请求签名（Header）

    返回：
        成功响应或 challenge 验证响应
    """
    settings = get_settings()
    body = await request.body()
    body_str = body.decode("utf-8")

    # 验证签名（如果配置了 verification_token）
    if settings.FEISHU_VERIFICATION_TOKEN and x_lark_signature:
        is_valid = verify_webhook_signature(
            timestamp=x_lark_request_timestamp or "",
            nonce=x_lark_request_nonce or "",
            encrypt_key=settings.FEISHU_VERIFICATION_TOKEN,
            body=body_str,
            signature=x_lark_signature,
        )

        if not is_valid:
            logger.warning("Invalid Feishu webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

    # 解析请求体
    try:
        data = json.loads(body_str)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in request body")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # URL 验证（首次配置回调地址时）
    if "challenge" in data:
        logger.info("Received Feishu challenge request")
        return {"challenge": data["challenge"]}

    # 解密消息（如果启用了加密）
    if "encrypt" in data and settings.FEISHU_ENCRYPT_KEY:
        try:
            encrypted = data["encrypt"]
            decrypted_str = decrypt_message(settings.FEISHU_ENCRYPT_KEY, encrypted)
            data = json.loads(decrypted_str)
        except Exception as e:
            logger.exception(f"Failed to decrypt message: {e}")
            raise HTTPException(status_code=400, detail="Failed to decrypt message")

    # 获取事件类型和数据
    header = data.get("header", {})
    event = data.get("event", {})
    event_type = header.get("event_type")

    logger.info(f"Received Feishu event: {event_type}")

    try:
        # 处理卡片按钮点击事件
        if event_type == "card.action.trigger":
            action = event.get("action", {})
            action_value = action.get("value", {})

            # 支持字符串类型的 value（需要解析 JSON）
            if isinstance(action_value, str):
                try:
                    action_value = json.loads(action_value)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON in action value: {action_value}")
                    action_value = {}

            user_id = event.get("operator", {}).get("open_id", "unknown")

            result = await handle_card_action(action_value, user_id)

            # 发送响应消息到群聊（可选）
            if result.get("success") and settings.FEISHU_CHAT_ID:
                await send_approval_response(
                    chat_id=settings.FEISHU_CHAT_ID,
                    task_id=action_value.get("task_id", "unknown"),
                    decision=action_value.get("decision", "unknown"),
                    approver=user_id,
                    result=result,
                )

        # 处理接收到的消息
        elif event_type == "im.message.receive_v1":
            message = event.get("message", {})
            await handle_message_receive(message)

        # 处理其他事件类型
        else:
            logger.debug(f"Unhandled event type: {event_type}")

    except Exception as e:
        logger.exception(f"Error processing Feishu event: {e}")
        # 仍然返回成功，避免飞书重试
        return {"code": 0, "msg": "error_logged"}

    # 返回成功响应
    return {"code": 0, "msg": "success"}


@router.get("/status")
async def feishu_status():
    """
    获取飞书集成状态。

    返回：
        包含飞书集成状态信息的字典

    示例：
        GET /api/v1/feishu/status
        返回：{
            "enabled": true,
            "connection_mode": "webhook",
            "healthy": true,
            "longconn": {...}
        }
    """

    settings = get_settings()

    if not settings.FEISHU_ENABLED:
        return {"enabled": False, "error": "Feishu integration is not enabled"}

    try:
        client = get_feishu_client()
        is_healthy = await client.check_feishu_health()

        # 获取长连接状态（简化检查）
        longconn_status = None
        if settings.FEISHU_CONNECTION_MODE in ["longconn", "auto"]:
            longconn_client = get_feishu_longconn_client()
            if longconn_client:
                # lark_longconn 没有 get_status()，只返回基本连接信息
                longconn_status = {
                    "connected": longconn_client.ws_client is not None,
                    "type": "lark_sdk"
                }

        return {
            "enabled": True,
            "connection_mode": settings.FEISHU_CONNECTION_MODE,
            "healthy": is_healthy,
            "app_id": client.app_id[:8] + "..." if client.app_id else None,
            "has_webhook_url": client.webhook_url is not None,
            "has_verification_token": client.verification_token is not None,
            "has_encrypt_key": client.encrypt_key is not None,
            "longconn": longconn_status,
        }

    except Exception as e:
        logger.exception(f"Error getting Feishu status: {e}")
        return {"enabled": False, "error": str(e)}


@router.post("/test-message")
async def send_test_message(text: str = "测试消息"):
    """
    发送测试消息到配置的飞书群聊。

    参数：
        text: 消息文本（默认为"测试消息"）

    返回：
        发送结果

    示例：
        POST /api/v1/feishu/test-message?text=Hello
    """

    settings = get_settings()

    if not settings.FEISHU_ENABLED:
        raise HTTPException(status_code=400, detail="Feishu integration is not enabled")

    if not settings.FEISHU_CHAT_ID:
        raise HTTPException(status_code=400, detail="FEISHU_CHAT_ID not configured")

    try:
        success = await send_notification(
            chat_id=settings.FEISHU_CHAT_ID, message=text, level="info"
        )

        if success:
            return {"success": True, "message": "Test message sent successfully"}
        else:
            return {"success": False, "message": "Failed to send test message"}

    except Exception as e:
        logger.exception(f"Error sending test message: {e}")
        raise HTTPException(status_code=500, detail=str(e))
