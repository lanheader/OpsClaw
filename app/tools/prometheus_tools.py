"""Prometheus工具集"""

from typing import Dict, Any, List
from datetime import datetime, timedelta


def query_cpu_usage(target: str = None, duration: str = "5m") -> Dict[str, Any]:
    """
    查询CPU使用率

    Args:
        target: 目标（Pod、Node等）
        duration: 时间范围

    Returns:
        CPU使用率数据
    """
    return {
        "metric": "cpu_usage",
        "target": target or "all",
        "duration": duration,
        "current": 45.5,
        "average": 42.3,
        "max": 78.9,
        "min": 12.1,
        "unit": "percent",
    }


def query_memory_usage(target: str = None, duration: str = "5m") -> Dict[str, Any]:
    """查询内存使用率"""
    return {
        "metric": "memory_usage",
        "target": target or "all",
        "duration": duration,
        "current": 62.3,
        "average": 58.7,
        "max": 85.2,
        "min": 45.6,
        "unit": "percent",
    }


def query_disk_usage(target: str = None) -> Dict[str, Any]:
    """查询磁盘使用率"""
    return {
        "metric": "disk_usage",
        "target": target or "all",
        "current": 78.9,
        "total": "100GB",
        "used": "78.9GB",
        "available": "21.1GB",
        "unit": "percent",
    }


def query_network_traffic(target: str = None, duration: str = "5m") -> Dict[str, Any]:
    """查询网络流量"""
    return {
        "metric": "network_traffic",
        "target": target or "all",
        "duration": duration,
        "in_bytes": 1024000,
        "out_bytes": 512000,
        "in_rate": "1MB/s",
        "out_rate": "500KB/s",
    }


def query_request_rate(service: str = None, duration: str = "5m") -> Dict[str, Any]:
    """查询请求速率"""
    return {
        "metric": "request_rate",
        "service": service or "all",
        "duration": duration,
        "current": 1250,
        "average": 1180,
        "max": 2340,
        "min": 890,
        "unit": "req/s",
    }


def query_error_rate(service: str = None, duration: str = "5m") -> Dict[str, Any]:
    """查询错误率"""
    return {
        "metric": "error_rate",
        "service": service or "all",
        "duration": duration,
        "current": 2.3,
        "average": 1.8,
        "max": 5.6,
        "min": 0.5,
        "unit": "percent",
    }


def query_latency(service: str = None, duration: str = "5m") -> Dict[str, Any]:
    """查询延迟"""
    return {
        "metric": "latency",
        "service": service or "all",
        "duration": duration,
        "p50": 45,
        "p90": 120,
        "p95": 180,
        "p99": 350,
        "unit": "ms",
    }


def calculate_growth_rate(metrics: List[float]) -> Dict[str, Any]:
    """
    计算增长率

    Args:
        metrics: 指标数据列表（按时间顺序）

    Returns:
        增长率分析结果
    """
    if not metrics or len(metrics) < 2:
        return {
            "error": "需要至少2个数据点",
            "growth_rate": 0.0,
        }

    # 简单的线性增长率计算
    first_value = metrics[0]
    last_value = metrics[-1]

    if first_value == 0:
        growth_rate = 0.0
    else:
        growth_rate = ((last_value - first_value) / first_value) * 100

    # 计算平均增长率（每个时间段）
    period_growth_rates = []
    for i in range(1, len(metrics)):
        if metrics[i - 1] != 0:
            rate = ((metrics[i] - metrics[i - 1]) / metrics[i - 1]) * 100
            period_growth_rates.append(rate)

    avg_period_growth = (
        sum(period_growth_rates) / len(period_growth_rates) if period_growth_rates else 0.0
    )

    return {
        "total_growth_rate": round(growth_rate, 2),
        "avg_period_growth_rate": round(avg_period_growth, 2),
        "data_points": len(metrics),
        "first_value": first_value,
        "last_value": last_value,
        "trend": "increasing" if growth_rate > 0 else "decreasing" if growth_rate < 0 else "stable",
        "unit": "percent",
    }


def predict_capacity(resource_type: str, days: int = 30) -> Dict[str, Any]:
    """
    预测资源容量

    Args:
        resource_type: 资源类型（cpu, memory, disk）
        days: 预测未来N天

    Returns:
        容量预测结果
    """
    # 模拟历史数据和预测
    if resource_type == "disk":
        return {
            "resource_type": "disk",
            "prediction_days": days,
            "current_usage": 78.9,
            "current_usage_gb": 78.9,
            "capacity_gb": 100.0,
            "daily_growth_rate": 0.8,
            "predicted_usage": {
                "7_days": 84.5,
                "14_days": 90.1,
                "30_days": 102.3,
            },
            "estimated_full_date": "2026-04-10",
            "days_until_full": 26,
            "recommendation": "建议在未来20天内扩容磁盘或清理数据",
            "confidence": 0.85,
        }
    elif resource_type == "memory":
        return {
            "resource_type": "memory",
            "prediction_days": days,
            "current_usage": 62.3,
            "capacity_gb": 16.0,
            "daily_growth_rate": 0.3,
            "predicted_usage": {
                "7_days": 64.4,
                "14_days": 66.5,
                "30_days": 71.3,
            },
            "estimated_full_date": "2026-06-15",
            "days_until_full": 92,
            "recommendation": "内存使用稳定，暂无扩容需求",
            "confidence": 0.78,
        }
    elif resource_type == "cpu":
        return {
            "resource_type": "cpu",
            "prediction_days": days,
            "current_usage": 45.5,
            "capacity_cores": 8,
            "daily_growth_rate": 0.2,
            "predicted_usage": {
                "7_days": 46.9,
                "14_days": 48.3,
                "30_days": 51.5,
            },
            "estimated_full_date": None,
            "days_until_full": None,
            "recommendation": "CPU使用率健康，无需扩容",
            "confidence": 0.72,
        }
    else:
        return {
            "error": f"不支持的资源类型: {resource_type}",
            "supported_types": ["cpu", "memory", "disk"],
        }


def analyze_trend(metric_name: str, duration: str = "7d") -> Dict[str, Any]:
    """
    趋势分析

    Args:
        metric_name: 指标名称（cpu_usage, memory_usage, disk_usage等）
        duration: 分析时间范围

    Returns:
        趋势分析结果
    """
    # 模拟历史数据
    if metric_name == "disk_usage":
        historical_data = [65.2, 67.8, 70.1, 72.5, 74.9, 76.8, 78.9]
        return {
            "metric": metric_name,
            "duration": duration,
            "data_points": len(historical_data),
            "historical_data": historical_data,
            "trend": "increasing",
            "growth_rate": 21.0,
            "avg_daily_growth": 2.28,
            "volatility": "low",
            "anomalies": [],
            "forecast_next_7_days": [81.2, 83.5, 85.8, 88.1, 90.4, 92.7, 95.0],
            "risk_level": "high",
            "recommendation": "磁盘使用率持续增长，建议尽快扩容或清理数据",
        }
    elif metric_name == "memory_usage":
        historical_data = [58.3, 59.1, 60.2, 61.5, 60.8, 62.1, 62.3]
        return {
            "metric": metric_name,
            "duration": duration,
            "data_points": len(historical_data),
            "historical_data": historical_data,
            "trend": "stable",
            "growth_rate": 6.9,
            "avg_daily_growth": 0.67,
            "volatility": "low",
            "anomalies": [],
            "forecast_next_7_days": [63.0, 63.7, 64.4, 65.1, 65.8, 66.5, 67.2],
            "risk_level": "medium",
            "recommendation": "内存使用率稳定增长，建议持续监控",
        }
    elif metric_name == "cpu_usage":
        historical_data = [42.1, 45.3, 43.8, 46.2, 44.5, 47.1, 45.5]
        return {
            "metric": metric_name,
            "duration": duration,
            "data_points": len(historical_data),
            "historical_data": historical_data,
            "trend": "fluctuating",
            "growth_rate": 8.1,
            "avg_daily_growth": 0.57,
            "volatility": "medium",
            "anomalies": [{"timestamp": "2026-03-13", "value": 47.1, "reason": "峰值负载"}],
            "forecast_next_7_days": [46.2, 46.9, 47.6, 48.3, 49.0, 49.7, 50.4],
            "risk_level": "low",
            "recommendation": "CPU使用率波动正常，无需特殊处理",
        }
    else:
        return {
            "error": f"不支持的指标: {metric_name}",
            "supported_metrics": ["cpu_usage", "memory_usage", "disk_usage"],
        }
