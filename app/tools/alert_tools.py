"""告警工具集

通过 AlertManager API 获取和管理告警。
当 AlertManager 未配置时，返回空列表并记录警告。
"""

from typing import Dict, Any, List


async def get_active_alerts() -> List[Dict[str, Any]]:
    """获取当前活跃的告警"""
    from app.integrations.alertmanager import get_alertmanager_client
    client = get_alertmanager_client()
    return await client.get_alerts(active=True)


async def get_resolved_alerts(duration: str = "1h") -> List[Dict[str, Any]]:
    """获取已解决的告警"""
    from app.integrations.alertmanager import get_alertmanager_client
    client = get_alertmanager_client()
    return await client.get_alerts(active=False)


async def get_alert_statistics(duration: str = "24h") -> Dict[str, Any]:
    """获取告警原始数据（聚合分析由 analyze-agent 完成）"""
    from app.integrations.alertmanager import get_alertmanager_client
    client = get_alertmanager_client()

    active = await client.get_alerts(active=True)
    silenced = await client.get_silences()

    return {
        "duration": duration,
        "total_active": len(active),
        "total_silenced": len(silenced),
        "active_alerts": active,
        "silenced_alerts": silenced,
    }


async def silence_alert(
    alert_name: str,
    duration: str = "1h",
    comment: str = "",
) -> Dict[str, Any]:
    """静默告警"""
    from app.integrations.alertmanager import get_alertmanager_client
    client = get_alertmanager_client()

    matchers = [
        {
            "name": "alertname",
            "value": alert_name,
            "isRegex": False,
        }
    ]

    return await client.create_silence(
        matchers=matchers,  # type: ignore[arg-type]
        duration=duration,
        comment=comment or f"Silenced by OpsAgent: {alert_name}",
    )
