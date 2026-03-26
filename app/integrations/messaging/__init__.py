"""
消息渠道抽象层

提供统一的消息处理接口，支持多种消息渠道（飞书、Slack、微信、钉钉等）。
"""

from app.integrations.messaging.base_channel import (
    BaseChannelAdapter,
    IncomingMessage,
    OutgoingMessage,
    ChannelContext,
    MessageType,
    MessageAction,
)

__all__ = [
    "BaseChannelAdapter",
    "IncomingMessage",
    "OutgoingMessage",
    "ChannelContext",
    "MessageType",
    "MessageAction",
]
