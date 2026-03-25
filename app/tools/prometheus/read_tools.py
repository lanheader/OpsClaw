"""
Prometheus 工具（新架构示例）

使用 BaseOpTool 基类和 @register_tool 装饰器。
支持 SDK → CLI 降级机制。
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from app.tools.base import (
    BaseOpTool,
    register_tool,
    OperationType,
    RiskLevel,
    ToolCategory,
    tool_error_response,
    tool_success_response,
)
from app.tools.fallback import get_prometheus_fallback
from app.utils.logger import get_logger, get_request_context

logger = get_logger(__name__)

# Try to import PrometheusToolFactory, but don't fail if it doesn't exist
try:
    from app.tools.prometheus.factory import PrometheusToolFactory, MetricType
except ImportError:
    PrometheusToolFactory = None
    MetricType = None


def _log_tool_start(tool_name: str, **kwargs):
    """记录工具开始执行的日志"""
    ctx = get_request_context()
    session_id = ctx.get('session_id', 'no-sess')
    params = {k: v for k, v in kwargs.items() if v is not None}
    logger.info(f"🔧 [{session_id}] 执行工具: {tool_name} | 参数: {params}")


def _log_tool_success(tool_name: str, result_count: int = None):
    """记录工具执行成功的日志"""
    ctx = get_request_context()
    session_id = ctx.get('session_id', 'no-sess')
    if result_count is not None:
        logger.info(f"✅ [{session_id}] 工具完成: {tool_name} | 返回 {result_count} 条数据")
    else:
        logger.info(f"✅ [{session_id}] 工具完成: {tool_name}")


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
        """执行工具操作"""
        _log_tool_start("query_cpu_usage", labels=labels, time_range=time_range)
        try:
            # 优先使用 SDK
            result = await self._execute_with_sdk(labels, time_range)
            _log_tool_success("query_cpu_usage")
            return result
        except Exception as e:
            logger.warning(f"Prometheus SDK 失败，降级到 CLI: {e}")
            try:
                # 降级到 CLI
                query = self._build_query("cpu", labels)
                result = await self.fallback.execute(
                    operation="query",
                    query=query,
                    time=time_range
                )
                _log_tool_success("query_cpu_usage")
                return result
            except Exception as fallback_error:
                return tool_error_response(
                    fallback_error, "query_cpu_usage",
                    context={"labels": labels, "time_range": time_range},
                    suggestion="请检查 Prometheus 服务是否正常运行"
                )

    async def _execute_with_sdk(
        self,
        labels: Optional[Dict[str, str]],
        time_range: str,
    ) -> Dict[str, Any]:
        """直接使用 CLI 降级（SDK 工厂未实现）"""
        # Prometheus SDK 工厂未实现，直接降级到 CLI
        raise NotImplementedError("Prometheus SDK not implemented, using CLI fallback")

        if result.get("success"):
            data = result.get("data", {})
            return tool_success_response(
                {
                    "metric": "cpu_usage",
                    "values": data,
                    "labels": labels,
                    "time_range": time_range,
                },
                "query_cpu_usage",
                source="prometheus-sdk"
            )
        else:
            raise Exception(result.get("error", "Unknown error"))

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
        _log_tool_start("query_memory_usage", labels=labels, time_range=time_range)
        try:
            result = await self._execute_with_sdk(labels, time_range)
            _log_tool_success("query_memory_usage")
            return result
        except Exception as e:
            logger.warning(f"Prometheus SDK 失败，降级到 CLI: {e}")
            try:
                query = self._build_query("memory", labels)
                result = await self.fallback.execute(
                    operation="query",
                    query=query,
                    time=time_range
                )
                _log_tool_success("query_memory_usage")
                return result
            except Exception as fallback_error:
                return tool_error_response(
                    fallback_error, "query_memory_usage",
                    context={"labels": labels, "time_range": time_range},
                    suggestion="请检查 Prometheus 服务是否正常运行"
                )

    async def _execute_with_sdk(
        self,
        labels: Optional[Dict[str, str]],
        time_range: str,
    ) -> Dict[str, Any]:
        """直接使用 CLI 降级（SDK 工厂未实现）"""
        # Prometheus SDK 工厂未实现，直接降级到 CLI
        raise NotImplementedError("Prometheus SDK not implemented, using CLI fallback")

        if result.get("success"):
            data = result.get("data", {})
            return tool_success_response(
                {
                    "metric": "memory_usage",
                    "values": data,
                    "labels": labels,
                    "time_range": time_range,
                },
                "query_memory_usage",
                source="prometheus-sdk"
            )
        else:
            raise Exception(result.get("error", "Unknown error"))

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
    description=(
        "执行 PromQL 范围查询\n"
        "时间参数支持多种格式:\n"
        "- 相对时间: '5m' (5分钟前), '1h' (1小时前), '1d' (1天前)\n"
        "- 负相对时间: '-1h' (从现在往后1小时，仅用于 end)\n"
        "- 特殊值: 'now' (当前时间)\n"
        "- 绝对时间: '2024-01-01T00:00:00Z' (ISO 8601格式)\n\n"
        "示例:\n"
        "- query_range(query='up') - 查询当前状态\n"
        "- query_range(query='rate(http_requests_total[5m])', start='1h') - 最近1小时\n"
        "- query_range(query='up', start='2024-01-01T00:00:00Z', end='2024-01-01T01:00:00Z') - 指定时间范围"
    ),
    examples=[
        "query_range(query='up')",
        "query_range(query='rate(http_requests_total[5m])', start='1h')",
        "query_range(query='up', start='2024-01-01T00:00:00Z', end='2024-01-01T01:00:00Z', step='1m')",
    ],
)
class QueryRangeTool(BaseOpTool):
    """
    PromQL 范围查询工具

    执行指定时间范围的 PromQL 查询。
    """

    def __init__(self):
        self.fallback = get_prometheus_fallback()

    async def execute(
        self,
        query: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        step: str = "15s",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("query_range", query=query, start=start, end=end, step=step)
        # Prometheus SDK 工厂未实现，直接使用 CLI 降级
        try:
            # 构建 CLI 命令
            cli = get_prometheus_fallback()
            cmd = cli.build_command(
                operation="query_range",
                query=query,
                start=start or "1h",
                end=end or "now",
                step=step,
            )

            # 执行命令
            result = await cli.execute(cmd)
            _log_tool_success("query_range")
            return result
        except Exception as e:
            logger.warning(f"Prometheus CLI 执行失败: {e}")
            return tool_error_response(
                str(e), "query_range",
                context={"query": query, "start": start, "end": end, "step": step},
                suggestion="请检查 PromQL 查询语法是否正确，以及 Prometheus 服务是否正常运行"
            )

    async def _execute_with_sdk(
        self,
        query: str,
        start: Optional[str],
        end: Optional[str],
        step: str,
    ) -> Dict[str, Any]:
        """使用 SDK 执行"""
        # 解析时间参数
        start_dt = None
        end_dt = None

        if start:
            start_lower = start.lower()
            if start_lower == "now":
                # 当前时间
                start_dt = datetime.now()
            elif start_lower.endswith("m") or start_lower.endswith("h") or start_lower.endswith("d"):
                # 相对时间，如 "5m", "1h", "1d"（视为负数，即从现在往前）
                start_dt = self._parse_relative_time(start)
            elif start.startswith("-"):
                # 相对时间，如 "-1h"
                start_dt = datetime.now() + timedelta(hours=int(start[1:-1]))
            else:
                # ISO 8601 格式
                start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))

        if end:
            end_lower = end.lower()
            if end_lower == "now":
                # 当前时间
                end_dt = datetime.now()
            elif end_lower.endswith("m") or end_lower.endswith("h") or end_lower.endswith("d"):
                # 相对时间，如 "5m", "1h", "1d"（视为负数，即从现在往前）
                end_dt = self._parse_relative_time(end)
            elif end.startswith("-"):
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
            return tool_success_response(
                {
                    "query": query,
                    "values": data,
                    "start": start,
                    "end": end,
                    "step": step,
                },
                "query_range",
                source="prometheus-sdk"
            )
        else:
            raise Exception(result.get("error", "Unknown error"))

    @staticmethod
    def _parse_relative_time(time_str: str) -> datetime:
        """
        解析相对时间字符串（如 "5m", "1h", "1d"）为 datetime

        Args:
            time_str: 时间字符串，如 "5m"（5分钟前）, "1h"（1小时前）, "1d"（1天前）

        Returns:
            解析后的 datetime 对象
        """
        time_lower = time_str.lower()
        value = int(time_lower[:-1])

        if time_lower.endswith("m"):
            return datetime.now() - timedelta(minutes=value)
        elif time_lower.endswith("h"):
            return datetime.now() - timedelta(hours=value)
        elif time_lower.endswith("d"):
            return datetime.now() - timedelta(days=value)
        else:
            # 如果不匹配已知格式，尝试解析为 ISO 格式
            try:
                return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError(f"不支持的时间格式: {time_str}。支持的格式: 5m, 1h, 1d, -1h, ISO 8601")


__all__ = [
    "QueryCPUUsageTool",
    "QueryMemoryUsageTool",
    "QueryRangeTool",
]
