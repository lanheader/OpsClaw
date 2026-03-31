"""AlertManager 集成模块"""

from .client import AlertManagerClient, get_alertmanager_client

__all__ = ["AlertManagerClient", "get_alertmanager_client"]
