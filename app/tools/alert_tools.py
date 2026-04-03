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
    """获取告警统计"""
    from app.integrations.alertmanager import get_alertmanager_client
    client = get_alertmanager_client()

    active = await client.get_alerts(active=True)
    silenced = await client.get_silences()

    # 按严重级别统计
    by_severity = {}  # type: ignore[var-annotated]
    by_service = {}  # type: ignore[var-annotated]
    top_alerts = {}  # type: ignore[var-annotated]

    for alert in active:
        severity = alert.get("labels", {}).get("severity", "unknown")
        by_severity[severity] = by_severity.get(severity, 0) + 1

        alert_name = alert.get("labels", {}).get("alertname", "unknown")
        top_alerts[alert_name] = top_alerts.get(alert_name, 0) + 1

        # 尝试提取 service
        service = (
            alert.get("labels", {}).get("service")
            or alert.get("labels", {}).get("job")
            or "unknown"
        )
        by_service[service] = by_service.get(service, 0) + 1

    # 排序 top_alerts
    sorted_top = sorted(top_alerts.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "duration": duration,
        "total_active": len(active),
        "total_silenced": len(silenced),
        "by_severity": by_severity,
        "by_service": by_service,
        "top_alerts": [{"name": name, "count": count} for name, count in sorted_top],
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
