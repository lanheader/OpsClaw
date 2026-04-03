"""
Prometheus 工具（使用 HTTP API）

使用 BaseOpTool 基类和 @register_tool 装饰器。
使用 PrometheusClient HTTP API 进行查询。
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
from app.integrations.prometheus.client import get_prometheus_client
from app.models.database import SessionLocal
from app.models.system_setting import SystemSetting
from app.utils.logger import get_logger, get_request_context

logger = get_logger(__name__)


def _get_prometheus_url_from_db() -> Optional[str]:
    """从数据库获取 Prometheus URL 配置"""
    try:
        db = SessionLocal()
        setting = db.query(SystemSetting).filter(
            SystemSetting.key == "prometheus.url"
        ).first()
        if setting:
            return setting.value  # type: ignore[return-value]
    except Exception as e:
        logger.warning(f"从数据库读取 Prometheus URL 失败: {e}")
    finally:
        if 'db' in locals():
            db.close()
    return None


def _log_tool_start(tool_name: str, **kwargs):  # type: ignore[no-untyped-def]
    """记录工具开始执行的日志"""
    ctx = get_request_context()
    session_id = ctx.get('session_id', 'no-sess')
    params = {k: v for k, v in kwargs.items() if v is not None}
    logger.info(f"🔧 [{session_id}] 执行工具: {tool_name} | 参数: {params}")


def _log_tool_success(tool_name: str, result_count: int = None):  # type: ignore[assignment]
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
        "query_cpu_usage(labels={'pod': 'nginx'})",
    ],
)
class QueryCPUUsageTool(BaseOpTool):
    """
    查询 CPU 使用率工具

    查询指定标签过滤的 CPU 使用率指标。
    """

    def __init__(self, db=None):  # type: ignore[no-untyped-def]
        self.db = db

    async def execute(  # type: ignore[no-untyped-def]
        self,
        labels: Optional[Dict[str, str]] = None,
        time_range: str = "1h",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("query_cpu_usage", labels=labels, time_range=time_range)
        try:
            # 动态获取 Prometheus 客户端（使用最新配置）
            prometheus_url = _get_prometheus_url_from_db()
            client = get_prometheus_client(base_url=prometheus_url)
            logger.info(f"📡 [Prometheus] 使用 URL: {client.base_url}")

            # 构建 PromQL 查询
            query = self._build_query("cpu", labels)

            # 执行即时查询
            result = await client.query(query=query)

            if result.get("status") == "success":
                data = result.get("data", {})
                _log_tool_success("query_cpu_usage", result_count=len(data.get("result", [])))
                return tool_success_response(
                    {
                        "metric": "cpu_usage",
                        "values": data.get("result", []),
                        "labels": labels,
                        "time_range": time_range,
                    },
                    "query_cpu_usage",
                    source="prometheus-http-api"
                )
            else:
                raise Exception(result.get("error", "Unknown error"))

        except Exception as e:
            logger.error(f"Prometheus CPU 查询失败: {e}")
            return tool_error_response(
                e, "query_cpu_usage",
                context={"labels": labels, "time_range": time_range},
                suggestion="请检查 Prometheus 服务是否正常运行"
            )

    def _build_query(self, metric_type: str, labels: Optional[Dict[str, str]]) -> str:
        """构建 PromQL 查询"""
        query = 'rate(container_cpu_usage_seconds_total[5m])'

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
        "query_memory_usage(labels={'pod': 'nginx'})",
    ],
)
class QueryMemoryUsageTool(BaseOpTool):
    """
    查询内存使用率工具

    查询指定标签过滤的内存使用率指标。
    """

    def __init__(self, db=None):  # type: ignore[no-untyped-def]
        self.db = db

    async def execute(  # type: ignore[no-untyped-def]
        self,
        labels: Optional[Dict[str, str]] = None,
        time_range: str = "1h",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("query_memory_usage", labels=labels, time_range=time_range)
        try:
            # 动态获取 Prometheus 客户端（使用最新配置）
            prometheus_url = _get_prometheus_url_from_db()
            client = get_prometheus_client(base_url=prometheus_url)
            logger.info(f"📡 [Prometheus] 使用 URL: {client.base_url}")

            # 构建 PromQL 查询
            query = self._build_query("memory", labels)

            # 执行即时查询
            result = await client.query(query=query)

            if result.get("status") == "success":
                data = result.get("data", {})
                _log_tool_success("query_memory_usage", result_count=len(data.get("result", [])))
                return tool_success_response(
                    {
                        "metric": "memory_usage",
                        "values": data.get("result", []),
                        "labels": labels,
                        "time_range": time_range,
                    },
                    "query_memory_usage",
                    source="prometheus-http-api"
                )
            else:
                raise Exception(result.get("error", "Unknown error"))

        except Exception as e:
            logger.error(f"Prometheus 内存查询失败: {e}")
            return tool_error_response(
                e, "query_memory_usage",
                context={"labels": labels, "time_range": time_range},
                suggestion="请检查 Prometheus 服务是否正常运行"
            )

    def _build_query(self, metric_type: str, labels: Optional[Dict[str, str]]) -> str:
        """构建 PromQL 查询"""
        query = 'rate(container_memory_working_set_bytes[5m])'

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
        "- 特殊值: 'now' (当前时间)\n"
        "- 绝对时间: '2024-01-01T00:00:00Z' (ISO 8601格式)\n\n"
        "示例:\n"
        "- query_range(query='up') - 最近1小时\n"
        "- query_range(query='rate(http_requests_total[5m])', start='2h', end='1h') - 2小时前到1小时前\n"
        "- query_range(query='up', start='2024-01-01T00:00:00Z', end='2024-01-01T01:00:00Z', step='1m') - 指定时间范围"
    ),
    examples=[
        "query_range(query='up')",
        "query_range(query='rate(http_requests_total[5m])', start='2h')",
        "query_range(query='up', start='2024-01-01T00:00:00Z', end='2024-01-01T01:00:00Z', step='1m')",
    ],
)
class QueryRangeTool(BaseOpTool):
    """
    PromQL 范围查询工具

    执行指定时间范围的 PromQL 查询。
    """

    def __init__(self, db=None):  # type: ignore[no-untyped-def]
        self.db = db

    async def execute(  # type: ignore[no-untyped-def]
        self,
        query: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        step: str = "15s",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("query_range", query=query, start=start, end=end, step=step)

        try:
            # 动态获取 Prometheus 客户端（使用最新配置）
            prometheus_url = _get_prometheus_url_from_db()
            client = get_prometheus_client(base_url=prometheus_url)
            logger.info(f"📡 [Prometheus] 使用 URL: {client.base_url}")

            # 解析时间参数
            start_dt = self._parse_time_param(start) if start else datetime.now() - timedelta(hours=1)
            end_dt = self._parse_time_param(end) if end else datetime.now()

            # 执行范围查询
            result = await client.query_range(
                query=query,
                start=start_dt,
                end=end_dt,
                step=step
            )

            if result.get("status") == "success":
                data = result.get("data", {})
                result_count = len(data.get("result", []))
                _log_tool_success("query_range", result_count=result_count)
                return tool_success_response(
                    {
                        "query": query,
                        "values": data.get("result", []),
                        "start": start_dt.isoformat(),
                        "end": end_dt.isoformat(),
                        "step": step,
                    },
                    "query_range",
                    source="prometheus-http-api"
                )
            else:
                raise Exception(result.get("error", "Unknown error"))

        except Exception as e:
            logger.error(f"Prometheus 范围查询失败: {e}")
            return tool_error_response(
                str(e), "query_range",  # type: ignore[arg-type]
                context={"query": query, "start": start, "end": end, "step": step},
                suggestion="请检查 PromQL 查询语法是否正确，以及 Prometheus 服务是否正常运行"
            )

    def _parse_time_param(self, time_str: str) -> datetime:
        """
        解析时间参数

        Args:
            time_str: 时间字符串，支持多种格式

        Returns:
            解析后的 datetime 对象
        """
        time_lower = time_str.lower()

        # 特殊值: now
        if time_lower == "now":
            return datetime.now()

        # 相对时间: 5m, 1h, 1d（从现在往前）
        if time_lower.endswith("m"):
            value = int(time_lower[:-1])
            return datetime.now() - timedelta(minutes=value)
        elif time_lower.endswith("h"):
            value = int(time_lower[:-1])
            return datetime.now() - timedelta(hours=value)
        elif time_lower.endswith("d"):
            value = int(time_lower[:-1])
            return datetime.now() - timedelta(days=value)

        # 负相对时间: -1h（从现在往后）
        if time_lower.startswith("-") and (time_lower.endswith("h") or time_lower.endswith("m")):
            value = int(time_lower[1:-1])
            if time_lower.endswith("h"):
                return datetime.now() + timedelta(hours=value)
            else:
                return datetime.now() + timedelta(minutes=value)

        # ISO 8601 格式
        try:
            return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(
                f"不支持的时间格式: {time_str}。"
                f"支持的格式: now, 5m, 1h, 1d, -1h, ISO 8601"
            )


__all__ = [
    "QueryCPUUsageTool",
    "QueryMemoryUsageTool",
    "QueryRangeTool",
]
