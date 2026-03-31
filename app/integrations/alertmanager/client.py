"""
AlertManager API 客户端

封装 AlertManager REST API 调用，用于：
- 获取活跃告警
- 获取已解决告警
- 获取静默规则
- 创建静默规则
"""

import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.utils.logger import get_logger
from app.integrations.http_client import get_shared_http_client

logger = get_logger(__name__)


class AlertManagerClient:
    """AlertManager API 客户端"""

    def __init__(self, base_url: Optional[str] = None, timeout: int = 30):
        """
        Args:
            base_url: AlertManager 地址（如 http://alertmanager:9093）
            timeout: 请求超时（秒）
        """
        settings = get_settings()
        self.base_url = (base_url or getattr(settings, 'ALERTMANAGER_URL', None) or "").rstrip("/")
        self.timeout = timeout

    @property
    def is_available(self) -> bool:
        """AlertManager 是否配置"""
        return bool(self.base_url)

    async def get_alerts(
        self,
        active: bool = True,
        silenced: bool = False,
        inhibited: bool = False,
        unprocessed: bool = False,
        filter_query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取告警列表

        Args:
            active: 只返回活跃告警
            silenced: 包含已静默的告警
            inhibited: 包含已抑制的告警
            unprocessed: 包含未处理的告警
            filter_query: 过滤表达式（如 alertname="HighCPU"）

        Returns:
            告警列表
        """
        if not self.is_available:
            logger.warning("AlertManager 未配置，返回空列表")
            return []

        params = {
            "active": str(active).lower(),
            "silenced": str(silenced).lower(),
            "inhibited": str(inhibited).lower(),
            "unprocessed": str(unprocessed).lower(),
        }
        if filter_query:
            params["filter"] = filter_query

        try:
            client = get_shared_http_client(timeout=self.timeout)
            resp = await client.get(f"{self.base_url}/api/v2/alerts", params=params)
            if resp.status_code == 200:
                data = resp.json()
                logger.info(f"获取到 {len(data)} 条告警")
                return data
            else:
                logger.error(f"获取告警失败: HTTP {resp.status_code}")
                return []
        except Exception as e:
            logger.error(f"连接 AlertManager 失败: {e}")
            return []

    async def get_silences(
        self,
        matchers: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取静默规则列表

        Args:
            matchers: 过滤匹配器

        Returns:
            静默规则列表
        """
        if not self.is_available:
            return []

        params = {}
        if matchers:
            params["filter"] = matchers

        try:
            client = get_shared_http_client(timeout=self.timeout)
            resp = await client.get(f"{self.base_url}/api/v2/silences", params=params)
            if resp.status_code == 200:
                return resp.json()
            logger.error(f"获取静默规则失败: HTTP {resp.status_code}")
            return []
        except Exception as e:
            logger.error(f"连接 AlertManager 失败: {e}")
            return []

    async def create_silence(
        self,
        matchers: List[Dict[str, str]],
        starts_at: Optional[str] = None,
        ends_at: Optional[str] = None,
        duration: str = "1h",
        created_by: str = "ops-agent",
        comment: str = "",
    ) -> Dict[str, Any]:
        """
        创建静默规则

        Args:
            matchers: 匹配器列表，如 [{"name": "alertname", "value": "HighCPU", "isRegex": false}]
            starts_at: 开始时间（ISO 8601），默认为当前时间
            ends_at: 结束时间（ISO 8601），或使用 duration
            duration: 持续时间（如 1h, 30m, 2d）
            created_by: 创建者
            comment: 备注

        Returns:
            创建结果
        """
        if not self.is_available:
            return {"success": False, "message": "AlertManager 未配置"}

        if not starts_at:
            starts_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        if not ends_at:
            unit = duration[-1]
            value = int(duration[:-1])
            seconds = {"h": 3600, "m": 60, "d": 86400}.get(unit, 3600) * value
            ends_at = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")

        payload = {
            "matchers": matchers,
            "startsAt": starts_at,
            "endsAt": ends_at,
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "createdBy": created_by,
            "comment": comment,
        }

        try:
            client = get_shared_http_client(timeout=self.timeout)
            resp = await client.post(f"{self.base_url}/api/v2/silences", json=payload)
            if resp.status_code in (200, 201):
                data = resp.json()
                logger.info(f"静默规则创建成功: silence_id={data.get('silenceID')}")
                return {"success": True, "silence_id": data.get("silenceID")}
            else:
                logger.error(f"创建静默规则失败: HTTP {resp.status_code}, {resp.text}")
                return {"success": False, "message": f"HTTP {resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"创建静默规则失败: {e}")
            return {"success": False, "message": str(e)}

    async def delete_silence(self, silence_id: str) -> Dict[str, Any]:
        """删除静默规则"""
        if not self.is_available:
            return {"success": False, "message": "AlertManager 未配置"}

        try:
            client = get_shared_http_client(timeout=self.timeout)
            resp = await client.delete(f"{self.base_url}/api/v2/silence/{silence_id}")
            if resp.status_code == 200:
                return {"success": True}
            logger.error(f"删除静默规则失败: HTTP {resp.status_code}")
            return {"success": False, "message": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "message": str(e)}


# 全局单例
_client: Optional[AlertManagerClient] = None


def get_alertmanager_client() -> AlertManagerClient:
    """获取 AlertManager 客户端单例"""
    global _client
    if _client is None:
        _client = AlertManagerClient()
    return _client


__all__ = ["AlertManagerClient", "get_alertmanager_client"]
