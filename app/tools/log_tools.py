"""日志工具集"""

from typing import Dict, Any, List
from datetime import datetime, timedelta


def query_logs(
    service: str = None, level: str = None, duration: str = "5m", limit: int = 100
) -> List[str]:
    """
    查询日志

    Args:
        service: 服务名称
        level: 日志级别（INFO, WARN, ERROR）
        duration: 时间范围
        limit: 返回条数

    Returns:
        日志列表
    """
    now = datetime.now()
    logs = [
        f"{(now - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')} INFO Application started",
        f"{(now - timedelta(minutes=4)).strftime('%Y-%m-%d %H:%M:%S')} INFO Processing request",
        f"{(now - timedelta(minutes=3)).strftime('%Y-%m-%d %H:%M:%S')} WARN High memory usage detected: 85%",
        f"{(now - timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S')} ERROR Connection timeout to database",
        f"{(now - timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M:%S')} ERROR Failed to process request: timeout",
    ]

    if level:
        logs = [log for log in logs if level.upper() in log]

    return logs[:limit]


def query_error_logs(service: str = None, duration: str = "5m") -> List[str]:
    """查询错误日志"""
    return query_logs(service=service, level="ERROR", duration=duration)


def query_warn_logs(service: str = None, duration: str = "5m") -> List[str]:
    """查询警告日志"""
    return query_logs(service=service, level="WARN", duration=duration)


def search_logs(keyword: str, service: str = None, duration: str = "5m") -> List[str]:
    """搜索日志"""
    all_logs = query_logs(service=service, duration=duration)
    return [log for log in all_logs if keyword.lower() in log.lower()]


def get_log_statistics(service: str = None, duration: str = "5m") -> Dict[str, Any]:
    """获取日志统计"""
    return {
        "service": service or "all",
        "duration": duration,
        "total_logs": 1250,
        "info_count": 980,
        "warn_count": 180,
        "error_count": 90,
        "error_rate": 7.2,
        "top_errors": [
            {"message": "Connection timeout", "count": 45},
            {"message": "Database error", "count": 23},
            {"message": "Request timeout", "count": 22},
        ],
    }
