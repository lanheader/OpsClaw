"""
Loki 工具（新架构示例）

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
from app.tools.fallback import get_loki_fallback

logger = logging.getLogger(__name__)


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
        """
        执行工具操作

        Args:
            query: LogQL 查询语句
            limit: 返回结果数量限制
            start: 开始时间（ISO 8601 格式或相对时间如 "-1h"）
            end: 结束时间（ISO 8601 格式或相对时间）

        Returns:
            执行结果字典
        """
        try:
            # 优先使用 SDK
            logger.info(f"Using Loki SDK to query logs: {query}")
            result = await self._execute_with_sdk(query, limit, start, end)
            return result
        except Exception as e:
            logger.warning(f"Loki SDK failed: {e}, falling back to CLI")
            # 降级到 CLI
            result = await self.fallback.execute(
                operation="query",
                query=query,
                limit=limit,
                start=start or "-1h",
                end=end or "now"
            )
            return result

    async def _execute_with_sdk(
        self,
        query: str,
        limit: int,
        start: Optional[str],
        end: Optional[str],
    ) -> Dict[str, Any]:
        """使用 SDK 执行"""
        # TODO: 实现真实的 Loki SDK 调用
        # 这里提供简化的实现

        return {
            "success": True,
            "data": {
                "query": query,
                "logs": [],  # 实际应从 SDK 获取
                "limit": limit,
                "start": start,
                "end": end,
            },
            "execution_mode": "sdk",
            "source": "loki-sdk",
        }


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
        """
        执行工具操作

        Args:
            namespace: Kubernetes 命名空间
            app: 应用名称
            limit: 返回结果数量限制

        Returns:
            执行结果字典
        """
        # 构建 LogQL 查询
        query_parts = ['level="error"']

        if namespace:
            query_parts.append(f'namespace="{namespace}"')
        if app:
            query_parts.append(f'app="{app}"')

        query = "{" + ",".join(query_parts) + "}"

        try:
            logger.info(f"Using Loki SDK to query error logs: {query}")
            result = await self._execute_with_sdk(query, limit)
            return result
        except Exception as e:
            logger.warning(f"Loki SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="query",
                query=query,
                limit=limit
            )
            return result

    async def _execute_with_sdk(
        self,
        query: str,
        limit: int,
    ) -> Dict[str, Any]:
        """使用 SDK 执行"""
        # TODO: 实现真实的 Loki SDK 调用

        return {
            "success": True,
            "data": {
                "query": query,
                "logs": [],  # 实际应从 SDK 获取
                "limit": limit,
            },
            "execution_mode": "sdk",
            "source": "loki-sdk",
        }


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
        """
        执行工具操作

        Args:
            pattern: 搜索模式（字符串或正则表达式）
            namespace: Kubernetes 命名空间
            app: 应用名称
            limit: 返回结果数量限制

        Returns:
            执行结果字典
        """
        # 构建 LogQL 查询（使用 |= 或 |~ 进行内容搜索）
        query_parts = []

        if namespace:
            query_parts.append(f'namespace="{namespace}"')
        if app:
            query_parts.append(f'app="{app}"')

        selector = "{" + ",".join(query_parts) + "}" if query_parts else "{"
        query = f'{selector} |= "{pattern}"'

        try:
            logger.info(f"Using Loki SDK to search logs: {query}")
            result = await self._execute_with_sdk(query, limit, pattern)
            return result
        except Exception as e:
            logger.warning(f"Loki SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="query",
                query=query,
                limit=limit
            )
            return result

    async def _execute_with_sdk(
        self,
        query: str,
        limit: int,
        pattern: str,
    ) -> Dict[str, Any]:
        """使用 SDK 执行"""
        # TODO: 实现真实的 Loki SDK 调用

        return {
            "success": True,
            "data": {
                "query": query,
                "pattern": pattern,
                "logs": [],  # 实际应从 SDK 获取
                "limit": limit,
            },
            "execution_mode": "sdk",
            "source": "loki-sdk",
        }


__all__ = [
    "QueryLogsTool",
    "QueryErrorLogsTool",
    "SearchLogsTool",
]
