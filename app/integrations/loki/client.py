# app/integrations/loki/client.py
"""用于日志聚合的 Loki 客户端"""

import logging
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import httpx

logger = logging.getLogger(__name__)


class LokiClient:
    """
    用于查询 Loki 日志的客户端。

    支持：
    - LogQL 查询
    - 日志流过滤
    - 时间范围查询
    - 基于标签的过滤
    """

    def __init__(self, base_url: str, timeout: int = 30):
        """
        初始化 Loki 客户端。

        参数：
            base_url: Loki 服务器 URL（例如 "http://loki:3100"）
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        limit: int = 1000,
        direction: str = "backward",
    ) -> Dict[str, Any]:
        """
        执行范围查询以获取日志。

        参数：
            query: LogQL 查询字符串
            start: 开始时间
            end: 结束时间
            limit: 返回的最大日志行数
            direction: "forward" 或 "backward"

        返回：
            包含日志结果的字典

        示例：
            result = await client.query_range(
                '{app="redis", level="error"}',
                start=now - timedelta(hours=1),
                end=now,
                limit=100
            )
        """
        url = f"{self.base_url}/loki/api/v1/query_range"
        params = {
            "query": query,
            "start": int(start.timestamp() * 1e9),  # 纳秒
            "end": int(end.timestamp() * 1e9),
            "limit": limit,
            "direction": direction,
        }

        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "success":
                logger.error(f"Loki query failed: {data.get('error')}")
                return {"status": "error", "error": data.get("error", "Unknown error")}

            return data

        except httpx.HTTPError as e:
            logger.exception(f"Loki HTTP error: {e}")
            return {"status": "error", "error": str(e)}
        except Exception as e:
            logger.exception(f"Loki query error: {e}")
            return {"status": "error", "error": str(e)}

    async def get_logs(
        self,
        labels: Dict[str, str],
        start: datetime,
        end: datetime,
        limit: int = 1000,
        level_filter: Optional[str] = None,
        keyword_filter: Optional[str] = None,
    ) -> List[str]:
        """
        使用标签和内容过滤获取日志。

        参数：
            labels: 标签过滤器（例如 {"app": "redis", "namespace": "prod"}）
            start: 开始时间
            end: 结束时间
            limit: 最大日志行数
            level_filter: 可选的日志级别过滤器（例如 "error"）
            keyword_filter: 可选的日志内容关键词

        返回：
            日志行列表

        示例：
            logs = await client.get_logs(
                labels={"app": "redis-prod", "namespace": "production"},
                start=now - timedelta(minutes=30),
                end=now,
                level_filter="error",
                keyword_filter="connection"
            )
        """
        # 构建 LogQL 查询
        label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
        query = f"{{{label_str}}}"

        # 添加行过滤器
        if level_filter:
            query += f' |= "{level_filter}"'

        if keyword_filter:
            query += f' |= "{keyword_filter}"'

        result = await self.query_range(query, start, end, limit)

        if result.get("status") == "success":
            return self._extract_log_lines(result)

        return []

    async def search_logs(
        self,
        app: str,
        namespace: str,
        keywords: List[str],
        start: datetime,
        end: datetime,
        limit: int = 1000,
    ) -> List[str]:
        """
        使用多个关键词搜索日志。

        参数：
            app: 应用名称
            namespace: Kubernetes 命名空间
            keywords: 要搜索的关键词列表
            start: 开始时间
            end: 结束时间
            limit: 最大日志行数

        返回：
            匹配的日志行列表

        示例：
            logs = await client.search_logs(
                app="user-service",
                namespace="production",
                keywords=["error", "timeout", "connection"],
                start=now - timedelta(hours=1),
                end=now
            )
        """
        # 构建包含多个关键词过滤器的查询
        query = f'{{app="{app}", namespace="{namespace}"}}'

        for keyword in keywords:
            query += f' |= "{keyword}"'

        result = await self.query_range(query, start, end, limit)

        if result.get("status") == "success":
            return self._extract_log_lines(result)

        return []

    async def get_error_logs(
        self, app: str, namespace: str, start: datetime, end: datetime, limit: int = 500
    ) -> List[str]:
        """
        获取应用的 error 级别日志。

        参数：
            app: 应用名称
            namespace: Kubernetes 命名空间
            start: 开始时间
            end: 结束时间
            limit: 最大日志行数

        返回：
            错误日志行列表

        示例：
            errors = await client.get_error_logs(
                app="redis-prod",
                namespace="production",
                start=now - timedelta(hours=1),
                end=now
            )
        """
        return await self.get_logs(
            labels={"app": app, "namespace": namespace},
            start=start,
            end=end,
            limit=limit,
            level_filter="error",
        )

    async def count_log_patterns(
        self, app: str, namespace: str, patterns: List[str], start: datetime, end: datetime
    ) -> Dict[str, int]:
        """
        统计不同日志模式的出现次数。

        参数：
            app: 应用名称
            namespace: Kubernetes 命名空间
            patterns: 要统计的模式列表
            start: 开始时间
            end: 结束时间

        返回：
            模式到计数的映射字典

        示例：
            counts = await client.count_log_patterns(
                app="redis-prod",
                namespace="production",
                patterns=["maxmemory", "connection refused", "timeout"],
                start=now - timedelta(hours=1),
                end=now
            )
            # 返回：{"maxmemory": 15, "connection refused": 3, "timeout": 0}
        """
        pattern_counts = {}

        for pattern in patterns:
            logs = await self.get_logs(
                labels={"app": app, "namespace": namespace},
                start=start,
                end=end,
                keyword_filter=pattern,
                limit=10000,  # 用于计数的高限制
            )
            pattern_counts[pattern] = len(logs)

        return pattern_counts

    async def check_loki_health(self) -> bool:
        """
        检查 Loki 是否健康且可达。

        返回：
            如果 Loki 健康则返回 True，否则返回 False
        """
        try:
            url = f"{self.base_url}/ready"
            response = await self._client.get(url)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Loki health check failed: {e}")
            return False

    def _extract_log_lines(self, result: Dict[str, Any]) -> List[str]:
        """
        从 Loki 查询结果中提取日志行。

        参数：
            result: Loki 查询结果

        返回：
            日志行列表
        """
        log_lines = []

        data = result.get("data", {})
        result_type = data.get("resultType", "")

        if result_type == "streams":
            streams = data.get("result", [])
            for stream in streams:
                values = stream.get("values", [])
                for timestamp, line in values:
                    log_lines.append(line)

        return log_lines

    async def close(self):
        """关闭 HTTP 客户端"""
        await self._client.aclose()

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()


# 单例实例
_loki_client: Optional[LokiClient] = None


def get_loki_client(base_url: Optional[str] = None) -> LokiClient:
    """
    获取单例 Loki 客户端实例。

    参数：
        base_url: Loki 服务器 URL（仅在首次调用时使用）

    返回：
        LokiClient 实例
    """
    global _loki_client

    if _loki_client is None:
        if base_url is None:
            base_url = os.getenv("LOKI_URL", "http://loki:3100")

        _loki_client = LokiClient(base_url=base_url)

    return _loki_client
