# app/api/v1/feishu.py
"""
飞书集成 API 端点（使用新架构）

旧端点已重定向到新架构的统一消息处理。
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Header, BackgroundTasks

from app.utils.logger import get_logger
from app.core.config import get_settings
from app.integrations.messaging.registry import get_channel_adapter
from app.integrations.messaging.base_channel import IncomingMessage
from app.integrations.messaging.message_processor import MessageProcessor

logger = get_logger(__name__)

router = APIRouter(prefix="/feishu", tags=["feishu"])


@router.get("/status")
async def get_feishu_status():
    """
    获取飞书集成状态

    返回飞书渠道的配置和连接状态
    """
    try:
        settings = get_settings()
        adapter = get_channel_adapter("feishu")

        if not adapter:
            return {
                "enabled": False,
                "connection_mode": "unknown",
                "healthy": False,
                "message": "飞书适配器未初始化"
            }

        # 判断连接模式
        connection_mode = "unknown"
        if settings.FEISHU_CONNECTION_MODE == "longconn":
            connection_mode = "long_connection"
        elif settings.FEISHU_CONNECTION_MODE == "webhook":
            connection_mode = "webhook"
        elif settings.FEISHU_CONNECTION_MODE == "auto":
            # auto 模式下，检查长连接是否启用
            if settings.FEISHU_LONG_CONNECTION_ENABLED:
                connection_mode = "long_connection"
            else:
                connection_mode = "webhook"

        # 检查长连接健康状态
        longconn_healthy = False
        if connection_mode == "long_connection":
            try:
                from app.integrations.feishu.lark_longconn import get_feishu_longconn_client
                client = get_feishu_longconn_client()
                longconn_healthy = client is not None and hasattr(client, 'ws_client') and client.ws_client is not None
            except Exception as e:
                logger.warning(f"⚠️ 检查长连接状态失败: {e}")
                longconn_healthy = False

        return {
            "enabled": adapter.enabled and settings.FEISHU_ENABLED,
            "connection_mode": connection_mode,
            "healthy": adapter.enabled and (
                connection_mode == "webhook" or longconn_healthy
            ),
            "longconn_healthy": longconn_healthy if connection_mode == "long_connection" else None,
            "app_id": settings.FEISHU_APP_ID[:10] + "..." if settings.FEISHU_APP_ID else None,
            "webhook_require_mention": settings.FEISHU_WEBHOOK_REQUIRE_MENTION,
            "reply_with_mention": settings.FEISHU_REPLY_WITH_MENTION,
            "message": _get_status_message(adapter.enabled, connection_mode, longconn_healthy)
        }
    except Exception as e:
        logger.exception(f"❌ 获取飞书状态失败: {e}")
        return {
            "enabled": False,
            "connection_mode": "unknown",
            "healthy": False,
            "message": f"获取状态失败: {str(e)}"
        }


def _get_status_message(enabled: bool, mode: str, longconn_healthy: bool) -> str:
    """生成状态消息"""
    if not enabled:
        return "飞书集成未启用"
    if mode == "long_connection":
        if longconn_healthy:
            return "飞书长连接正常运行"
        else:
            return "飞书长连接未连接或已断开"
    elif mode == "webhook":
        return "飞书 Webhook 模式已启用"
    else:
        return "飞书集成状态未知"


@router.post("/test-message")
async def send_test_message(text: str):
    """
    发送测试消息到飞书

    用于测试飞书集成是否正常工作
    """
    try:
        settings = get_settings()
        adapter = get_channel_adapter("feishu")

        if not adapter or not adapter.enabled:
            raise HTTPException(
                status_code=503,
                detail="飞书渠道未启用或配置错误"
            )

        # 获取测试用的 chat_id（从环境变量或配置中获取）
        test_chat_id = settings.FEISHU_TEST_CHAT_ID if hasattr(settings, 'FEISHU_TEST_CHAT_ID') else None

        if not test_chat_id:
            raise HTTPException(
                status_code=400,
                detail="未配置测试 chat_id，请在 .env 中设置 FEISHU_TEST_CHAT_ID"
            )

        # 构造测试消息
        from app.integrations.messaging.base_channel import OutgoingMessage, MessageType
        from app.integrations.feishu.message import build_formatted_reply_card

        card = build_formatted_reply_card(content=text)
        outgoing = OutgoingMessage(
            chat_id=test_chat_id,
            message_type=MessageType.CARD,
            content=card,
        )

        # 发送消息
        result = await adapter.send_message(outgoing)

        return {
            "success": True,
            "message": "测试消息已发送",
            "result": result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ 发送测试消息失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"发送测试消息失败: {str(e)}"
        )


@router.post("/callback")
async def feishu_callback_legacy(
    request: Request,
    background_tasks: BackgroundTasks,
    x_lark_request_timestamp: Optional[str] = Header(None),
    x_lark_request_nonce: Optional[str] = Header(None),
    x_lark_signature: Optional[str] = Header(None),
):
    """
    飞书 Webhook 回调端点（旧版本，已重定向到新架构）

    注意：此端点已废弃，请使用新架构：
    POST /api/v2/messaging/webhook/feishu

    为了向后兼容，此端点仍然保留，但内部会调用新架构的处理逻辑。
    """
    # 检查是否启用了新架构
    settings = get_settings()

    if settings.USE_NEW_MESSAGING_ARCH:
        # 使用新架构处理
        return await _process_with_new_architecture(
            request=request,
            background_tasks=background_tasks,
            x_lark_request_timestamp=x_lark_request_timestamp,
            x_lark_request_nonce=x_lark_request_nonce,
            x_lark_signature=x_lark_signature,
        )
    else:
        # 新架构未启用，返回错误提示
        raise HTTPException(
            status_code=503,
            detail=(
                "旧的消息处理架构已废弃。\n\n"
                "请启用新架构：在 .env 文件中设置 USE_NEW_MESSAGING_ARCH=true\n\n"
                "或使用新端点：POST /api/v2/messaging/webhook/feishu"
            )
        )


async def _process_with_new_architecture(
    request: Request,
    background_tasks: BackgroundTasks,
    x_lark_request_timestamp: Optional[str],
    x_lark_request_nonce: Optional[str],
    x_lark_signature: Optional[str],
):
    """使用新架构处理飞书消息"""
    # 获取飞书适配器
    adapter = get_channel_adapter("feishu")

    if not adapter or not adapter.enabled:
        raise HTTPException(
            status_code=503,
            detail="飞书渠道未启用或配置错误"
        )

    # 读取请求体
    body = await request.body()

    # 构造请求头字典
    headers = {
        "timestamp": x_lark_request_timestamp,
        "nonce": x_lark_request_nonce,
        "signature": x_lark_signature,
    }

    # 验证签名
    if not await adapter.verify_request(headers, body.decode()):
        logger.warning("❌ 飞书签名验证失败")
        raise HTTPException(
            status_code=401,
            detail="Invalid signature"
        )

    # 解析消息
    try:
        # 解密消息
        event_data = await adapter.decrypt_message(body.decode())

        # 解析为统一格式
        message = await adapter.parse_incoming_message(event_data)

        logger.info(
            f"📨 收到飞书消息: sender={message.sender_id}, "
            f"text={message.text[:50]}..."
        )

        # 异步处理消息
        processor = MessageProcessor(adapter)
        background_tasks.add_task(processor.process_message, message)

        # 立即返回成功（飞书要求 3 秒内响应）
        return {
            "code": 0,
            "msg": "success"
        }

    except Exception as e:
        logger.exception(f"❌ 消息处理失败: {e}")
        # 即使失败也返回成功，避免渠道重试
        return {
            "code": 0,
            "msg": "received"
        }
