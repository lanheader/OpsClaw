"""
统一消息 API 端点

提供跨渠道的统一消息处理接口。
"""

from fastapi import APIRouter, Request, HTTPException, Header, BackgroundTasks
from typing import Optional

from app.utils.logger import get_logger
from app.core.config import get_settings
from app.integrations.messaging.registry import get_channel_adapter, ChannelRegistry, list_available_channels
from app.integrations.messaging.message_processor import MessageProcessor
from app.integrations.messaging.base_channel import IncomingMessage

logger = get_logger(__name__)

router = APIRouter()


@router.post("/webhook/{channel_type}")
async def universal_webhook(
    channel_type: str,
    request: Request,
    background_tasks: BackgroundTasks,
    x_request_timestamp: Optional[str] = Header(None, alias="x_lark_request_timestamp"),
    x_request_nonce: Optional[str] = Header(None, alias="x_lark_request_nonce"),
    x_request_signature: Optional[str] = Header(None, alias="x_lark_signature"),
):
    """
    统一消息 Webhook 端点

    支持所有渠道的消息接收：

    - **飞书**: POST /api/v2/messaging/webhook/feishu
    - **Slack**: POST /api/v2/messaging/webhook/slack
    - **微信**: POST /api/v2/messaging/webhook/wechat

    请求头（渠道特定）：
    - 飞书：x_lark_request_timestamp, x_lark_request_nonce, x_lark_signature
    - Slack：x-slack-request-timestamp, x-slack-signature

    Args:
        channel_type: 渠道类型（feishu, slack, wechat, dingtalk）
        request: FastAPI 请求对象
        background_tasks: 后台任务

    Returns:
        {"code": 0, "msg": "success"}
    """
    # 1. 获取渠道适配器
    adapter = get_channel_adapter(channel_type)
    if not adapter:
        raise HTTPException(
            status_code=404,
            detail=f"Channel '{channel_type}' not found or not enabled"
        )

    if not adapter.enabled:
        raise HTTPException(
            status_code=403,
            detail=f"Channel '{channel_type}' is disabled"
        )

    # 2. 读取请求体
    body = await request.body()

    # 3. 构造请求头字典
    headers = {
        "timestamp": x_request_timestamp,
        "nonce": x_request_nonce,
        "signature": x_request_signature,
    }

    # 添加其他可能的请求头
    for key, value in request.headers.items():
        if key.startswith("x_") or key.startswith("X-"):
            if key not in ["x_lark_request_timestamp", "x_lark_request_nonce", "x_lark_signature"]:
                headers[key] = value

    # 4. 验证签名
    if not await adapter.verify_request(headers, body.decode()):
        logger.warning(f"❌ 签名验证失败: channel={channel_type}")
        raise HTTPException(
            status_code=401,
            detail="Invalid signature"
        )

    # 5. 解析消息
    try:
        # 解密消息（如果渠道加密）
        event_data = await adapter.decrypt_message(body.decode())

        # 解析为统一格式
        message = await adapter.parse_incoming_message(event_data)

        logger.info(
            f"📨 收到消息: channel={channel_type}, "
            f"sender={message.sender_id}, "
            f"text={message.text[:50]}..."
        )

        # 6. 异步处理消息（不阻塞响应）
        processor = MessageProcessor(adapter)

        # 使用后台任务处理消息
        background_tasks.add_task(processor.process_message, message)

        # 立即返回成功（飞书要求 3 秒内响应）
        return {
            "code": 0,
            "msg": "success"
        }

    except Exception as e:
        logger.exception(f"❌ 消息处理失败: channel={channel_type}, error={e}")
        # 即使失败也返回成功，避免渠道重试
        return {
            "code": 0,
            "msg": "received"
        }


@router.get("/channels")
async def list_channels():
    """
    列出所有可用的消息渠道

    Returns:
        {
            "channels": ["feishu", "slack", ...],
            "enabled": ["feishu"]
        }
    """
    return {
        "channels": list_available_channels(),
        "enabled": ChannelRegistry.get_enabled_channels()
    }


@router.get("/health/{channel_type}")
async def channel_health_check(channel_type: str):
    """
    检查指定渠道的健康状态

    Args:
        channel_type: 渠道类型

    Returns:
        健康状态信息
    """
    adapter = get_channel_adapter(channel_type)

    if not adapter:
        raise HTTPException(
            status_code=404,
            detail=f"Channel '{channel_type}' not found"
        )

    health_info = await adapter.health_check()

    return {
        "channel_type": channel_type,
        **health_info
    }
