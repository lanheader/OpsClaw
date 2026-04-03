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

    # ========== 通用方法 ==========

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
            # 处理布尔值（按 value_type 或 key 后缀判断）
            # 兼容存储格式: "1"/"0", "True"/"False", "true"/"false"
            if setting.value_type == "boolean" or key.endswith(".enabled"):
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.strip() in ("true", "1", "yes", "True")
                return bool(value)
            return value

        return default

    @staticmethod
    def set_setting(db: Session, key: str, value: str, value_type: str = "string") -> None:
        """
        设置系统设置值

        Args:
            db: 数据库会话
            key: 设置键
            value: 设置值
            value_type: 值类型
        """
        setting = db.query(SystemSetting).filter(
            SystemSetting.key == key
        ).first()

        if setting:
            setting.value = value  # type: ignore[assignment]
        else:
            setting = SystemSetting(
                key=key,
                value=value,
                value_type=value_type,
                category="kubernetes",
                name=key.split(".")[-1],
            )
            db.add(setting)

    # ========== Kubernetes 配置 ==========

    @staticmethod
    def is_k8s_enabled(db: Session) -> bool:
        """检查 K8s 集成是否启用"""
        return IntegrationConfig.get_setting(db, "k8s.enabled", False)  # type: ignore[no-any-return]

    @staticmethod
    def get_k8s_auth_mode(db: Session) -> str:
        """
        获取 K8s 认证模式

        Returns:
            "kubeconfig" (kubeconfig 内容) 或 "token" (ServiceAccount Token)
        """
        return IntegrationConfig.get_setting(db, "k8s.auth_mode", "kubeconfig")  # type: ignore[no-any-return]

    @staticmethod
    def get_k8s_kubeconfig(db: Session) -> Optional[str]:
        """获取 K8s kubeconfig 内容（直接存储在数据库中）"""
        return IntegrationConfig.get_setting(db, "k8s.kubeconfig")  # type: ignore[no-any-return]

    @staticmethod
    def get_k8s_token(db: Session) -> Optional[str]:
        """获取 K8s ServiceAccount Token"""
        return IntegrationConfig.get_setting(db, "k8s.token")  # type: ignore[no-any-return]

    @staticmethod
    def get_k8s_api_host(db: Session) -> Optional[str]:
        """获取 K8s API Server 地址"""
        return IntegrationConfig.get_setting(db, "k8s.api_host")  # type: ignore[no-any-return]

    @staticmethod
    def get_k8s_ca_cert(db: Session) -> Optional[str]:
        """获取 K8s CA 证书"""
        return IntegrationConfig.get_setting(db, "k8s.ca_cert")  # type: ignore[no-any-return]

    # ========== Prometheus 配置 ==========

    @staticmethod
    def is_prometheus_enabled(db: Session) -> bool:
        """检查 Prometheus 集成是否启用"""
        return IntegrationConfig.get_setting(db, "prometheus.enabled", False)  # type: ignore[no-any-return]

    @staticmethod
    def get_prometheus_url(db: Session) -> Optional[str]:
        """获取 Prometheus URL"""
        return IntegrationConfig.get_setting(db, "prometheus.url")  # type: ignore[no-any-return]

    # ========== Loki 配置 ==========

    @staticmethod
    def is_loki_enabled(db: Session) -> bool:
        """检查 Loki 集成是否启用"""
        return IntegrationConfig.get_setting(db, "loki.enabled", False)  # type: ignore[no-any-return]

    @staticmethod
    def get_loki_url(db: Session) -> Optional[str]:
        """获取 Loki URL"""
        return IntegrationConfig.get_setting(db, "loki.url")  # type: ignore[no-any-return]

    # ========== 配置字典 ==========

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
                "auth_mode": IntegrationConfig.get_k8s_auth_mode(db),
                "kubeconfig": IntegrationConfig.get_k8s_kubeconfig(db),
                "token": IntegrationConfig.get_k8s_token(db),
                "api_host": IntegrationConfig.get_k8s_api_host(db),
                "ca_cert": IntegrationConfig.get_k8s_ca_cert(db),
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
