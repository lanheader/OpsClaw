"""
渠道适配器模块

包含各渠道的适配器实现：
- 飞书适配器
- Slack 适配器（预留）
- 微信适配器（预留）
- 钉钉适配器（预留）
"""

from app.integrations.messaging.adapters.feishu_adapter import (
    FeishuChannelAdapter,
    create_feishu_adapter,
)

__all__ = [
    "FeishuChannelAdapter",
    "create_feishu_adapter",
]
