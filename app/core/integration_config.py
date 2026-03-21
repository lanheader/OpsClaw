"""
集成配置管理

从数据库读取集成服务的开关状态。
"""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.system_setting import SystemSetting

logger = logging.getLogger(__name__)


class IntegrationConfig:
    """集成配置管理（从数据库读取）"""

    @staticmethod
    def get_setting(db: Session, key: str, default: Any = None) -> Any:
        """
        获取系统设置值

        Args:
            db: 数据库会话
            key: 设置键
            default: 默认值

        Returns:
            设置值
        """
        setting = db.query(SystemSetting).filter(
            SystemSetting.key == key
        ).first()

        if setting:
            value = setting.value
            # 处理布尔值
            if setting.value_type == "boolean":
                return value.lower() in ("true", "1", "yes")
            return value

        return default

    @staticmethod
    def is_k8s_enabled(db: Session) -> bool:
        """检查 K8s 集成是否启用"""
        return IntegrationConfig.get_setting(db, "k8s.enabled", False)

    @staticmethod
    def is_prometheus_enabled(db: Session) -> bool:
        """检查 Prometheus 集成是否启用"""
        return IntegrationConfig.get_setting(db, "prometheus.enabled", False)

    @staticmethod
    def is_loki_enabled(db: Session) -> bool:
        """检查 Loki 集成是否启用"""
        return IntegrationConfig.get_setting(db, "loki.enabled", False)

    @staticmethod
    def get_prometheus_url(db: Session) -> Optional[str]:
        """获取 Prometheus URL"""
        return IntegrationConfig.get_setting(db, "prometheus.url")

    @staticmethod
    def get_loki_url(db: Session) -> Optional[str]:
        """获取 Loki URL"""
        return IntegrationConfig.get_setting(db, "loki.url")

    @staticmethod
    def get_config_dict(db: Session) -> Dict[str, Any]:
        """
        获取所有集成配置

        Returns:
            集成配置字典
        """
        return {
            "k8s": {
                "enabled": IntegrationConfig.is_k8s_enabled(db),
            },
            "prometheus": {
                "enabled": IntegrationConfig.is_prometheus_enabled(db),
                "url": IntegrationConfig.get_prometheus_url(db),
            },
            "loki": {
                "enabled": IntegrationConfig.is_loki_enabled(db),
                "url": IntegrationConfig.get_loki_url(db),
            },
        }


__all__ = [
    "IntegrationConfig",
]
