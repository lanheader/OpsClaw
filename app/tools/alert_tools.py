"""告警工具集"""

from typing import Dict, Any, List
from datetime import datetime, timedelta


def get_active_alerts() -> List[Dict[str, Any]]:
    """获取当前活跃的告警"""
    return [
        {
            "name": "HighMemoryUsage",
            "severity": "warning",
            "status": "firing",
            "duration": "5m",
            "labels": {
                "service": "app-service",
                "namespace": "default",
            },
            "annotations": {
                "summary": "Memory usage is above 80%",
                "description": "Current memory usage: 85%",
            },
            "started_at": (datetime.now() - timedelta(minutes=5)).isoformat(),
        },
        {
            "name": "HighCPUUsage",
            "severity": "warning",
            "status": "firing",
            "duration": "3m",
            "labels": {
                "service": "app-service",
                "namespace": "default",
            },
            "annotations": {
                "summary": "CPU usage is above 70%",
                "description": "Current CPU usage: 78%",
            },
            "started_at": (datetime.now() - timedelta(minutes=3)).isoformat(),
        },
    ]


def get_resolved_alerts(duration: str = "1h") -> List[Dict[str, Any]]:
    """获取已解决的告警"""
    return [
        {
            "name": "PodCrashLooping",
            "severity": "critical",
            "status": "resolved",
            "duration": "15m",
            "labels": {
                "pod": "app-pod-2",
                "namespace": "default",
            },
            "annotations": {
                "summary": "Pod is crash looping",
                "description": "Pod has restarted 5 times in 10 minutes",
            },
            "started_at": (datetime.now() - timedelta(hours=1)).isoformat(),
            "resolved_at": (datetime.now() - timedelta(minutes=45)).isoformat(),
        }
    ]


def get_alert_statistics(duration: str = "24h") -> Dict[str, Any]:
    """获取告警统计"""
    return {
        "duration": duration,
        "total_alerts": 45,
        "active_alerts": 2,
        "resolved_alerts": 43,
        "by_severity": {
            "critical": 5,
            "warning": 28,
            "info": 12,
        },
        "by_service": {
            "app-service": 23,
            "db-service": 12,
            "cache-service": 10,
        },
        "top_alerts": [
            {"name": "HighMemoryUsage", "count": 15},
            {"name": "HighCPUUsage", "count": 12},
            {"name": "SlowResponse", "count": 8},
        ],
    }


def silence_alert(alert_name: str, duration: str = "1h") -> Dict[str, Any]:
    """静默告警"""
    return {
        "success": True,
        "message": f"Alert {alert_name} silenced for {duration}",
        "alert_name": alert_name,
        "duration": duration,
    }
