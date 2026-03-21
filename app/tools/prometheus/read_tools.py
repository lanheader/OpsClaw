"""
Prometheus 工具（新架构示例）

使用 BaseOpTool 基类和 @register_tool 装饰器。
支持 SDK → CLI 降级机制。
"""

from typing import Dict, Any, Optional
import logging

from app.tools.base import (
    BaseOpTool,
    register_tool,
    OperationType,
    RiskLevel,
    ToolCategory,
)
from app.tools.fallback import get_prometheus_fallback

logger = logging.getLogger(__name__)


@register_tool(
    group="prometheus.query",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["prometheus.view"],
    description="查询 CPU 使用率指标",
    examples=[
        "query_cpu_usage(labels={'namespace': 'default'})",
        "query_cpu_usage(labels={'pod': 'nginx'}, time_range='1h')",
    ],
)
class QueryCPUUsageTool(BaseOpTool):
    """
    查询 CPU 使用率工具

    查询指定标签过滤的 CPU 使用率指标。
    """

    def __init__(self):
        self.fallback = get_prometheus_fallback()

    async def execute(
        self,
        labels: Optional[Dict[str, str]] = None,
        time_range: str = "1h",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行工具操作

        Args:
            labels: 标签过滤
            time_range: 时间范围（如 "1h", "30m"）

        Returns:
            执行结果字典
        """
        try:
            # 优先使用 SDK
            logger.info(f"Using Prometheus SDK to query CPU usage")
            result = await self._execute_with_sdk(labels, time_range)
            return result
        except Exception as e:
            logger.warning(f"Prometheus SDK failed: {e}, falling back to CLI")
            # 降级到 CLI
            query = self._build_query("cpu", labels)
            result = await self.fallback.execute(
                operation="query",
                query=query,
                time=time_range
            )
            return result

    async def _execute_with_sdk(
        self,
        labels: Optional[Dict[str, str]],
        time_range: str,
    ) -> Dict[str, Any]:
        """使用 SDK 执行"""
        from app.tools.prometheus.factory import PrometheusToolFactory, MetricType

        result = await PrometheusToolFactory.query_metric(
            metric_type=MetricType.CPU,
            labels=labels,
            time_range=time_range,
        )

        if result.get("success"):
            data = result.get("data", {})
            return {
                "success": True,
                "data": {
                    "metric": "cpu_usage",
                    "values": data,
                    "labels": labels,
                    "time_range": time_range,
                },
                "execution_mode": "sdk",
                "source": "prometheus-sdk",
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "metric": "cpu_usage",
            }

    def _build_query(self, metric_type: str, labels: Optional[Dict[str, str]]) -> str:
        """构建 PromQL 查询"""
        query = f'rate(container_cpu_usage_seconds_total[5m])'

        if labels:
            label_filters = ",".join(f'{k}="{v}"' for k, v in labels.items())
            query = f'{query}{{{label_filters}}}'

        return query


@register_tool(
    group="prometheus.query",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["prometheus.view"],
    description="查询内存使用率指标",
    examples=[
        "query_memory_usage(labels={'namespace': 'default'})",
        "query_memory_usage(time_range='30m')",
    ],
)
class QueryMemoryUsageTool(BaseOpTool):
    """
    查询内存使用率工具

    查询指定标签过滤的内存使用率指标。
    """

    def __init__(self):
        self.fallback = get_prometheus_fallback()

    async def execute(
        self,
        labels: Optional[Dict[str, str]] = None,
        time_range: str = "1h",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        try:
            logger.info(f"Using Prometheus SDK to query memory usage")
            result = await self._execute_with_sdk(labels, time_range)
            return result
        except Exception as e:
            logger.warning(f"Prometheus SDK failed: {e}, falling back to CLI")
            query = self._build_query("memory", labels)
            result = await self.fallback.execute(
                operation="query",
                query=query,
                time=time_range
            )
            return result

    async def _execute_with_sdk(
        self,
        labels: Optional[Dict[str, str]],
        time_range: str,
    ) -> Dict[str, Any]:
        """使用 SDK 执行"""
        from app.tools.prometheus.factory import PrometheusToolFactory, MetricType

        result = await PrometheusToolFactory.query_metric(
            metric_type=MetricType.MEMORY,
            labels=labels,
            time_range=time_range,
        )

        if result.get("success"):
            data = result.get("data", {})
            return {
                "success": True,
                "data": {
                    "metric": "memory_usage",
                    "values": data,
                    "labels": labels,
                    "time_range": time_range,
                },
                "execution_mode": "sdk",
                "source": "prometheus-sdk",
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "metric": "memory_usage",
            }

    def _build_query(self, metric_type: str, labels: Optional[Dict[str, str]]) -> str:
        """构建 PromQL 查询"""
        query = f'rate(container_memory_working_set_bytes[5m])'

        if labels:
            label_filters = ",".join(f'{k}="{v}"' for k, v in labels.items())
            query = f'{query}{{{label_filters}}}'

        return query


@register_tool(
    group="prometheus.query",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["prometheus.view"],
    description="执行 PromQL 范围查询",
    examples=[
        "query_range(query='rate(http_requests_total[5m])', start='-1h', step='1m')",
        "query_range(query='up', start='2024-01-01T00:00:00Z', end='2024-01-01T01:00:00Z')",
    ],
)
class QueryRangeTool(BaseOpTool):
    """
    PromQL 范围查询工具

    执行指定时间范围的 PromQL 查询。
    """

    def __init__(self):
        from app.tools.prometheus.factory import PrometheusToolFactory
        self.factory = PrometheusToolFactory
        self.fallback = get_prometheus_fallback()

    async def execute(
        self,
        query: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        step: str = "15s",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行工具操作

        Args:
            query: PromQL 查询语句
            start: 开始时间（ISO 8601 格式或相对时间如 "-1h"）
            end: 结束时间（ISO 8601 格式或相对时间）
            step: 查询步长

        Returns:
            执行结果字典
        """
        try:
            logger.info(f"Using Prometheus SDK to execute range query: {query}")
            result = await self._execute_with_sdk(query, start, end, step)
            return result
        except Exception as e:
            logger.warning(f"Prometheus SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="query_range",
                query=query,
                start=start or "-1h",
                end=end or "now",
                step=step
            )
            return result

    async def _execute_with_sdk(
        self,
        query: str,
        start: Optional[str],
        end: Optional[str],
        step: str,
    ) -> Dict[str, Any]:
        """使用 SDK 执行"""
        from datetime import datetime, timedelta

        # 解析时间参数
        start_dt = None
        end_dt = None

        if start:
            if start.startswith("-"):
                # 相对时间，如 "-1h"
                start_dt = datetime.now() + timedelta(hours=int(start[1:-1]))
            else:
                # ISO 8601 格式
                start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))

        if end:
            if end.startswith("-"):
                end_dt = datetime.now() + timedelta(hours=int(end[1:-1]))
            else:
                end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))

        result = await self.factory.query_range(
            query=query,
            start=start_dt,
            end=end_dt,
            step=step,
        )

        if result.get("success"):
            data = result.get("data", {})
            return {
                "success": True,
                "data": {
                    "query": query,
                    "values": data,
                    "start": start,
                    "end": end,
                    "step": step,
                },
                "execution_mode": "sdk",
                "source": "prometheus-sdk",
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "query": query,
            }


__all__ = [
    "QueryCPUUsageTool",
    "QueryMemoryUsageTool",
    "QueryRangeTool",
]
