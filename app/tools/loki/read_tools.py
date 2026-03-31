"""
Loki 工具（新架构示例）

使用 BaseOpTool 基类和 @register_tool 装饰器。
支持 SDK → CLI 降级机制。
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from app.integrations.loki.client import get_loki_client
from app.tools.base import (
    BaseOpTool,
    register_tool,
    OperationType,
    RiskLevel,
    ToolCategory,
    tool_error_response,
    tool_success_response,
)
from app.tools.fallback import get_loki_fallback
from app.utils.logger import get_logger, get_request_context

logger = get_logger(__name__)


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
        logger.info(f"✅ [{session_id}] 工具完成: {tool_name} | 返回 {result_count} 条日志")
    else:
        logger.info(f"✅ [{session_id}] 工具完成: {tool_name}")


@register_tool(
    group="loki.query",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["loki.view"],
    description="查询 Loki 日志",
    examples=[
        "query_logs(query='{app=\"api\",level=\"error\"}')",
        "query_logs(query='{namespace=\"default\"}', limit=100)",
    ],
)
class QueryLogsTool(BaseOpTool):
    """
    Loki 日志查询工具

    执行 LogQL 查询语句获取日志。
    """

    def __init__(self):
        self.fallback = get_loki_fallback()

    async def execute(
        self,
        query: str,
        limit: int = 1000,
        start: Optional[str] = None,
        end: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("query_logs", query=query, limit=limit, start=start, end=end)
        try:
            # 优先使用 SDK
            result = await self._execute_with_sdk(query, limit, start, end)
            _log_tool_success("query_logs", len(result.get("data", {}).get("logs", [])))
            return result
        except Exception as e:
            logger.warning(f"Loki SDK 失败，降级到 CLI: {e}")
            try:
                # 降级到 CLI
                result = await self.fallback.execute(
                    operation="query",
                    query=query,
                    limit=limit,
                    start=start or "-1h",
                    end=end or "now"
                )
                _log_tool_success("query_logs")
                return result
            except Exception as fallback_error:
                return tool_error_response(
                    fallback_error, "query_logs",
                    context={"query": query, "limit": limit, "start": start, "end": end},
                    suggestion="请检查 LogQL 查询语法是否正确，以及 Loki 服务是否正常运行"
                )

    async def _execute_with_sdk(
        self,
        query: str,
        limit: int,
        start: Optional[str],
        end: Optional[str],
    ) -> Dict[str, Any]:
        """使用 SDK 执行 Loki 查询"""
        try:
            client = get_loki_client()

            # 解析时间参数
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)  # 默认查询最近 1 小时

            if end:
                # 支持相对时间如 "-1h", "-30m" 或绝对时间
                end_time = self._parse_time(end, end_time)
            if start:
                start_time = self._parse_time(start, end_time)

            # 调用 Loki 客户端
            result = await client.query_range(
                query=query,
                start=start_time,
                end=end_time,
                limit=limit,
            )

            if result.get("status") == "error":
                raise Exception(result.get("error", "Loki query failed"))

            # 提取日志行
            logs = client._extract_log_lines(result)

            return tool_success_response(
                {
                    "query": query,
                    "logs": logs,
                    "log_count": len(logs),
                    "limit": limit,
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                },
                "query_logs",
                source="loki-sdk"
            )

        except Exception as e:
            logger.error(f"Loki SDK 查询失败: {e}")
            raise

    def _parse_time(self, time_str: str, reference: datetime) -> datetime:
        """解析时间字符串"""
        if time_str == "now":
            return datetime.now()

        # 相对时间格式: -1h, -30m, -2d
        if time_str.startswith("-"):
            try:
                value = int(time_str[1:-1])
                unit = time_str[-1]
                if unit == "h":
                    return reference - timedelta(hours=value)
                elif unit == "m":
                    return reference - timedelta(minutes=value)
                elif unit == "d":
                    return reference - timedelta(days=value)
            except (ValueError, IndexError):
                pass

        # ISO 格式时间
        try:
            return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        except ValueError:
            pass

        # 无法解析，返回默认值
        logger.warning(f"无法解析时间字符串: {time_str}, 使用默认值")
        return reference - timedelta(hours=1)


@register_tool(
    group="loki.query",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["loki.view"],
    description="查询错误级别日志",
    examples=[
        "query_error_logs(namespace='default')",
        "query_error_logs(app='api', limit=500)",
    ],
)
class QueryErrorLogsTool(BaseOpTool):
    """
    错误日志查询工具

    快速查询错误级别的日志。
    """

    def __init__(self):
        self.fallback = get_loki_fallback()

    async def execute(
        self,
        namespace: Optional[str] = None,
        app: Optional[str] = None,
        limit: int = 1000,
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("query_error_logs", namespace=namespace, app=app, limit=limit)

        # 构建 LogQL 查询
        query_parts = ['level="error"']

        if namespace:
            query_parts.append(f'namespace="{namespace}"')
        if app:
            query_parts.append(f'app="{app}"')

        query = "{" + ",".join(query_parts) + "}"

        try:
            result = await self._execute_with_sdk(query, limit)
            _log_tool_success("query_error_logs", len(result.get("data", {}).get("logs", [])))
            return result
        except Exception as e:
            logger.warning(f"Loki SDK 失败，降级到 CLI: {e}")
            try:
                result = await self.fallback.execute(
                    operation="query",
                    query=query,
                    limit=limit
                )
                _log_tool_success("query_error_logs")
                return result
            except Exception as fallback_error:
                return tool_error_response(
                    fallback_error, "query_error_logs",
                    context={"namespace": namespace, "app": app, "query": query},
                    suggestion="请检查 Loki 服务是否正常运行"
                )

    async def _execute_with_sdk(
        self,
        query: str,
        limit: int,
    ) -> Dict[str, Any]:
        """使用 SDK 执行错误日志查询"""
        try:
            client = get_loki_client()
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)  # 默认查询最近 1 小时

            # 调用 Loki 客户端
            result = await client.query_range(
                query=query,
                start=start_time,
                end=end_time,
                limit=limit,
            )

            if result.get("status") == "error":
                raise Exception(result.get("error", "Loki query failed"))

            # 提取日志行
            logs = client._extract_log_lines(result)

            return tool_success_response(
                {
                    "query": query,
                    "logs": logs,
                    "log_count": len(logs),
                    "limit": limit,
                },
                "query_error_logs",
                source="loki-sdk"
            )

        except Exception as e:
            logger.error(f"Loki SDK 查询失败: {e}")
            raise


@register_tool(
    group="loki.query",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["loki.view"],
    description="搜索日志内容",
    examples=[
        "search_logs(pattern='connection timeout')",
        "search_logs(pattern='NullPointerException', app='api')",
    ],
)
class SearchLogsTool(BaseOpTool):
    """
    日志内容搜索工具

    在日志中搜索指定的字符串或正则表达式。
    """

    def __init__(self):
        self.fallback = get_loki_fallback()

    async def execute(
        self,
        pattern: str,
        namespace: Optional[str] = None,
        app: Optional[str] = None,
        limit: int = 1000,
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("search_logs", pattern=pattern, namespace=namespace, app=app, limit=limit)

        # 构建 LogQL 查询（使用 |= 或 |~ 进行内容搜索）
        query_parts = []

        if namespace:
            query_parts.append(f'namespace="{namespace}"')
        if app:
            query_parts.append(f'app="{app}"')

        selector = "{" + ",".join(query_parts) + "}" if query_parts else "{"
        query = f'{selector} |= "{pattern}"'

        try:
            result = await self._execute_with_sdk(query, limit, pattern)
            _log_tool_success("search_logs", len(result.get("data", {}).get("logs", [])))
            return result
        except Exception as e:
            logger.warning(f"Loki SDK 失败，降级到 CLI: {e}")
            try:
                result = await self.fallback.execute(
                    operation="query",
                    query=query,
                    limit=limit
                )
                _log_tool_success("search_logs")
                return result
            except Exception as fallback_error:
                return tool_error_response(
                    fallback_error, "search_logs",
                    context={"pattern": pattern, "namespace": namespace, "app": app, "query": query},
                    suggestion="请检查 Loki 服务是否正常运行"
                )

    async def _execute_with_sdk(
        self,
        query: str,
        limit: int,
        pattern: str,
    ) -> Dict[str, Any]:
        """使用 SDK 执行日志搜索"""
        try:
            client = get_loki_client()
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)  # 默认查询最近 1 小时

            # 调用 Loki 客户端
            result = await client.query_range(
                query=query,
                start=start_time,
                end=end_time,
                limit=limit,
            )

            if result.get("status") == "error":
                raise Exception(result.get("error", "Loki query failed"))

            # 提取日志行
            logs = client._extract_log_lines(result)

            return tool_success_response(
                {
                    "query": query,
                    "pattern": pattern,
                    "logs": logs,
                    "log_count": len(logs),
                    "limit": limit,
                },
                "search_logs",
                source="loki-sdk"
            )

        except Exception as e:
            logger.error(f"Loki SDK 搜索失败: {e}")
            raise


__all__ = [
    "QueryLogsTool",
    "QueryErrorLogsTool",
    "SearchLogsTool",
]
