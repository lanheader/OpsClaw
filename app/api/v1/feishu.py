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
