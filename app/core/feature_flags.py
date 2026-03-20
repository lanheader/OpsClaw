# app/core/feature_flags.py
"""用于 v1 到 v2 渐进式迁移的功能开关系统"""

import os
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class FeatureFlags:
    """
    用于控制 v1/v2 工作流路由的功能开关系统。

    支持：
    - 全局默认工作流版本
    - 插件特定的覆盖
    - 环境变量配置
    - 功能特定的开关
    """

    def __init__(self):
        """从环境变量初始化功能开关"""
        # 默认工作流版本（v1 或 v2）
        self.default_version = os.getenv("DEFAULT_WORKFLOW_VERSION", "v1")

        # 插件特定的覆盖（逗号分隔的列表）
        v2_plugins_str = os.getenv("V2_PLUGINS", "")
        self.v2_plugins: List[str] = [p.strip() for p in v2_plugins_str.split(",") if p.strip()]

        # 功能开关
        self.v2_inspection_enabled = os.getenv("V2_INSPECTION_ENABLED", "false").lower() == "true"
        self.v2_healing_enabled = os.getenv("V2_HEALING_ENABLED", "false").lower() == "true"
        self.v2_security_enabled = os.getenv("V2_SECURITY_ENABLED", "true").lower() == "true"

        logger.info(
            f"FeatureFlags initialized: default={self.default_version}, "
            f"v2_plugins={self.v2_plugins}, "
            f"inspection={self.v2_inspection_enabled}, "
            f"healing={self.v2_healing_enabled}"
        )

    def get_workflow_version(self, plugin_name: str, task_type: Optional[str] = None) -> str:
        """
        确定为插件使用哪个工作流版本。

        优先级：
        1. 插件特定的覆盖（V2_PLUGINS 环境变量）
        2. 任务类型功能开关（V2_INSPECTION_ENABLED 等）- 仅当提供 task_type 且默认为 v2 时
        3. 全局默认（DEFAULT_WORKFLOW_VERSION）

        参数：
            plugin_name: 插件名称
            task_type: 任务类型（可选）

        返回：
            "v1" 或 "v2"
        """
        # 检查插件特定的覆盖
        if plugin_name in self.v2_plugins:
            logger.debug(f"Plugin {plugin_name} uses v2 (plugin override)")
            return "v2"

        # 如果默认为 v2，检查任务类型特定的开关以可能降级到 v1
        if self.default_version == "v2" and task_type:
            # Inspection 开关：仅适用于 scheduled_inspection
            if task_type == "scheduled_inspection" and not self.v2_inspection_enabled:
                logger.debug(f"Plugin {plugin_name} uses v1 (inspection disabled)")
                return "v1"

            # Healing 开关：适用于 manual_command 和 emergency_response
            if (
                task_type in ["manual_command", "emergency_response"]
                and not self.v2_healing_enabled
            ):
                logger.debug(f"Plugin {plugin_name} uses v1 (healing disabled)")
                return "v1"

        # 使用全局默认值
        logger.debug(f"Plugin {plugin_name} uses {self.default_version} (default)")
        return self.default_version

    def is_v2_enabled_for_plugin(self, plugin_name: str) -> bool:
        """
        检查特定插件是否启用 v2 工作流。

        参数：
            plugin_name: 插件名称

        返回：
            如果启用 v2 则返回 True，否则返回 False
        """
        return self.get_workflow_version(plugin_name) == "v2"

    def get_v2_plugins(self) -> List[str]:
        """
        获取启用 v2 的插件列表。

        返回：
            插件名称列表
        """
        return self.v2_plugins.copy()

    def add_v2_plugin(self, plugin_name: str):
        """
        Add a plugin to v2 enabled list (runtime override).

        Args:
            plugin_name: Name of the plugin to enable
        """
        if plugin_name not in self.v2_plugins:
            self.v2_plugins.append(plugin_name)
            logger.info(f"Added {plugin_name} to v2 plugins")

    def remove_v2_plugin(self, plugin_name: str):
        """
        Remove a plugin from v2 enabled list (runtime override).

        Args:
            plugin_name: Name of the plugin to disable
        """
        if plugin_name in self.v2_plugins:
            self.v2_plugins.remove(plugin_name)
            logger.info(f"Removed {plugin_name} from v2 plugins")

    def enable_all_v2(self):
        """
        Enable v2 for all plugins (sets default to v2).

        WARNING: This is for production rollout only.
        """
        self.default_version = "v2"
        logger.warning("V2 enabled globally for all plugins")

    def rollback_to_v1(self):
        """
        Rollback to v1 for all plugins (emergency rollback).

        Clears v2 plugin list and sets default to v1.
        """
        self.default_version = "v1"
        self.v2_plugins.clear()
        logger.warning("ROLLBACK: V1 enabled globally, all v2 plugins cleared")

    def get_config_summary(self) -> Dict[str, any]:
        """
        Get current feature flag configuration summary.

        Returns:
            Dict with configuration details
        """
        return {
            "default_version": self.default_version,
            "v2_plugins": self.v2_plugins,
            "v2_plugins_count": len(self.v2_plugins),
            "features": {
                "inspection": self.v2_inspection_enabled,
                "healing": self.v2_healing_enabled,
                "security": self.v2_security_enabled,
            },
        }


# Singleton instance
_feature_flags: Optional[FeatureFlags] = None


def get_feature_flags() -> FeatureFlags:
    """
    Get singleton FeatureFlags instance.

    Returns:
        FeatureFlags instance
    """
    global _feature_flags

    if _feature_flags is None:
        _feature_flags = FeatureFlags()

    return _feature_flags
