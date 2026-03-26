"""
消息渠道适配器注册表

管理所有渠道适配器的注册、获取和初始化。
"""

from typing import Dict, Optional, List
from app.utils.logger import get_logger

from app.integrations.messaging.base_channel import BaseChannelAdapter

logger = get_logger(__name__)


class ChannelRegistry:
    """
    渠道适配器注册表

    使用单例模式管理所有渠道适配器。
    """

    _adapters: Dict[str, BaseChannelAdapter] = {}

    @classmethod
    def register(cls, adapter: BaseChannelAdapter) -> None:
        """
        注册渠道适配器

        Args:
            adapter: 渠道适配器实例

        Raises:
            ValueError: 如果渠道类型已存在
        """
        if adapter.channel_type is None:
            raise ValueError("Adapter must have a channel_type")

        if adapter.channel_type in cls._adapters:
            logger.warning(
                f"渠道适配器已存在，将被覆盖: {adapter.channel_type}"
            )

        cls._adapters[adapter.channel_type] = adapter
        logger.info(f"✅ 注册渠道适配器: {adapter.channel_type}")

    @classmethod
    def get(cls, channel_type: str) -> Optional[BaseChannelAdapter]:
        """
        获取渠道适配器

        Args:
            channel_type: 渠道类型（feishu, slack, wechat, etc.）

        Returns:
            渠道适配器实例，如果不存在则返回 None
        """
        return cls._adapters.get(channel_type)

    @classmethod
    def list_channels(cls) -> List[str]:
        """
        列出所有已注册的渠道

        Returns:
            渠道类型列表
        """
        return list(cls._adapters.keys())

    @classmethod
    def get_enabled_channels(cls) -> List[str]:
        """
        列出所有启用的渠道

        Returns:
            启用的渠道类型列表
        """
        return [
            ct for ct, adapter in cls._adapters.items()
            if adapter.enabled
        ]

    @classmethod
    def clear(cls) -> None:
        """清空所有适配器（主要用于测试）"""
        cls._adapters.clear()
        logger.info("清空渠道适配器注册表")


# 全局初始化函数
def initialize_channels() -> None:
    """
    初始化所有渠道适配器

    根据配置文件启用相应的渠道。
    """
    from app.core.config import get_settings
    settings = get_settings()

    logger.info("🔧 初始化消息渠道...")

    # 飞书
    if settings.FEISHU_ENABLED:
        try:
            from app.integrations.messaging.adapters.feishu_adapter import (
                create_feishu_adapter
            )

            feishu_adapter = create_feishu_adapter({
                "enabled": True,
                "app_id": settings.FEISHU_APP_ID,
                "app_secret": settings.FEISHU_APP_SECRET,
                "verification_token": settings.FEISHU_VERIFICATION_TOKEN,
                "encrypt_key": settings.FEISHU_ENCRYPT_KEY,
            })
            ChannelRegistry.register(feishu_adapter)
        except Exception as e:
            logger.error(f"❌ 飞书适配器初始化失败: {e}")

    # Slack（预留）
    # if settings.SLACK_ENABLED:
    #     try:
    #         from app.integrations.messaging.adapters.slack_adapter import (
    #             create_slack_adapter
    #         )
    #
    #         slack_adapter = create_slack_adapter({...})
    #         ChannelRegistry.register(slack_adapter)
    #     except Exception as e:
    #         logger.error(f"❌ Slack 适配器初始化失败: {e}")

    # 微信（预留）
    # 钉钉（预留）

    enabled_count = len(ChannelRegistry.get_enabled_channels())
    total_count = len(ChannelRegistry.list_channels())

    logger.info(f"✅ 消息渠道初始化完成: {enabled_count}/{total_count} 个渠道已启用")


# 便捷函数
def get_channel_adapter(channel_type: str) -> Optional[BaseChannelAdapter]:
    """
    获取渠道适配器（便捷函数）

    如果适配器未初始化，尝试自动初始化。

    Args:
        channel_type: 渠道类型

    Returns:
        渠道适配器实例，如果不存在则返回 None
    """
    adapter = ChannelRegistry.get(channel_type)
    if adapter is None:
        # 尝试自动初始化渠道
        logger.debug(f"渠道 {channel_type} 未初始化，尝试自动初始化...")
        try:
            initialize_channels()
            adapter = ChannelRegistry.get(channel_type)
        except Exception as e:
            logger.error(f"自动初始化渠道失败: {e}")
    return adapter


def list_available_channels() -> List[str]:
    """
    列出所有可用的渠道（便捷函数）

    Returns:
        渠道类型列表
    """
    return ChannelRegistry.list_channels()
