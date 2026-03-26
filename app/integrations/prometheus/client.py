# app/integrations/prometheus/client.py
"""用于指标采集的 Prometheus 客户端"""

import logging
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import httpx

logger = logging.getLogger(__name__)


class PrometheusClient:
    """
    用于查询 Prometheus 指标的客户端。

    支持：
    - 即时查询（当前指标值）
    - 范围查询（一段时间内的指标值）
    - 指标元数据查找
    """

    def __init__(self, base_url: str, timeout: int = 30):
        """
        初始化 Prometheus 客户端。

        参数：
            base_url: Prometheus 服务器 URL（例如 "http://prometheus:9090"）
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def query(self, query: str, time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        执行即时查询。

        参数：
            query: PromQL 查询字符串
            time: 可选时间戳（默认为当前时间）

        返回：
            包含查询结果的字典

        示例：
            result = await client.query('up{job="redis"}')
            # 返回：{'status': 'success', 'data': {'resultType': 'vector', 'result': [...]}}
        """
        url = f"{self.base_url}/api/v1/query"
        params = {"query": query}

        if time:
            params["time"] = time.timestamp()

        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "success":
                logger.error(f"Prometheus query failed: {data.get('error')}")
                return {"status": "error", "error": data.get("error", "Unknown error")}

            return data

        except httpx.HTTPError as e:
            logger.exception(f"Prometheus HTTP error: {e}")
            return {"status": "error", "error": str(e)}
        except Exception as e:
            logger.exception(f"Prometheus query error: {e}")
            return {"status": "error", "error": str(e)}

    async def query_range(
        self, query: str, start: datetime, end: datetime, step: str = "15s"
    ) -> Dict[str, Any]:
        """
        执行范围查询。

        参数：
            query: PromQL 查询字符串
            start: 开始时间
            end: 结束时间
            step: 查询分辨率步长（例如 "15s"、"1m"）

        返回：
            包含时间序列数据的字典

        示例：
            result = await client.query_range(
                'rate(http_requests_total[5m])',
                start=now - timedelta(hours=1),
                end=now,
                step="1m"
            )
        """
        url = f"{self.base_url}/api/v1/query_range"
        params = {"query": query, "start": start.timestamp(), "end": end.timestamp(), "step": step}

        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "success":
                logger.error(f"Prometheus range query failed: {data.get('error')}")
                return {"status": "error", "error": data.get("error", "Unknown error")}

            return data

        except httpx.HTTPError as e:
            logger.exception(f"Prometheus HTTP error: {e}")
            return {"status": "error", "error": str(e)}
        except Exception as e:
            logger.exception(f"Prometheus range query error: {e}")
            return {"status": "error", "error": str(e)}

    async def get_metric_current_value(
        self, metric_name: str, labels: Optional[Dict[str, str]] = None
    ) -> Optional[float]:
        """
        获取指标的当前值。

        参数：
            metric_name: 指标名称
            labels: 可选标签过滤器

        返回：
            当前指标值，如果未找到则为 None

        示例：
            value = await client.get_metric_current_value(
                'redis_memory_used_bytes',
                labels={'instance': 'redis-prod:6379'}
            )
        """
        # 使用标签构建查询
        if labels:
            label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
            query = f"{metric_name}{{{label_str}}}"
        else:
            query = metric_name

        result = await self.query(query)

        if result.get("status") == "success":
            data = result.get("data", {})
            results = data.get("result", [])

            if results:
                # 返回第一个结果的值
                value = results[0].get("value", [None, None])[1]
                try:
                    return float(value) if value is not None else None
                except (ValueError, TypeError):
                    return None

        return None

    async def get_metrics_for_plugin(
        self, plugin_name: str, plugin_type: str, metric_names: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """
        获取插件的多个指标。

        参数：
            plugin_name: 插件标识符
            plugin_type: 插件类型（redis、mysql 等）
            metric_names: 可选的要获取的特定指标列表

        返回：
            指标名称到当前值的映射字典

        示例：
            metrics = await client.get_metrics_for_plugin(
                'redis-prod',
                'redis',
                ['redis_memory_used_bytes', 'redis_connected_clients']
            )
            # 返回：{'redis_memory_used_bytes': 12345678, 'redis_connected_clients': 42}
        """
        if metric_names is None:
            # 按插件类型的默认指标
            metric_names = self._get_default_metrics(plugin_type)

        metrics = {}

        for metric_name in metric_names:
            # 尝试使用插件名称作为标签进行查询
            value = await self.get_metric_current_value(
                metric_name, labels={"instance": plugin_name}
            )

            if value is not None:
                metrics[metric_name] = value
            else:
                # 尝试不带标签（用于聚合指标）
                value = await self.get_metric_current_value(metric_name)
                if value is not None:
                    metrics[metric_name] = value

        return metrics

    async def check_prometheus_health(self) -> bool:
        """
        检查 Prometheus 是否健康且可达。

        返回：
            如果 Prometheus 健康则返回 True，否则返回 False
        """
        try:
            url = f"{self.base_url}/-/healthy"
            response = await self._client.get(url)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Prometheus health check failed: {e}")
            return False

    def _get_default_metrics(self, plugin_type: str) -> List[str]:
        """
        获取插件类型的默认指标。

        参数：
            plugin_type: 插件类型

        返回：
            默认指标名称列表
        """
        default_metrics = {
            "redis": [
                "redis_memory_used_bytes",
                "redis_connected_clients",
                "redis_blocked_clients",
                "redis_keyspace_hits_total",
                "redis_keyspace_misses_total",
                "redis_uptime_in_seconds",
            ],
            "mysql": [
                "mysql_global_status_threads_connected",
                "mysql_global_status_queries",
                "mysql_global_status_slow_queries",
                "mysql_global_status_innodb_row_lock_waits",
                "mysql_global_status_uptime",
            ],
            "nginx": [
                "nginx_connections_active",
                "nginx_connections_reading",
                "nginx_connections_writing",
                "nginx_connections_waiting",
                "nginx_http_requests_total",
            ],
            "microservice": [
                "http_requests_total",
                "http_request_duration_seconds",
                "http_requests_in_flight",
                "process_cpu_seconds_total",
                "process_resident_memory_bytes",
            ],
        }

        return default_metrics.get(plugin_type, [])

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
_prometheus_client: Optional[PrometheusClient] = None


def get_prometheus_client(base_url: Optional[str] = None, db=None) -> PrometheusClient:
    """
    获取单例 Prometheus 客户端实例。

    参数：
        base_url: Prometheus 服务器 URL（仅在首次调用时使用）
        db: 数据库会话（用于读取系统设置）

    返回：
        PrometheusClient 实例
    """
    global _prometheus_client

    if _prometheus_client is None:
        if base_url is None:
            # 1. 优先从环境变量读取
            base_url = os.getenv("PROMETHEUS_URL")

            # 2. 如果环境变量不存在，从数据库读取
            if base_url is None and db is not None:
                from app.models.system_setting import SystemSetting
                setting = db.query(SystemSetting).filter(
                    SystemSetting.key == "prometheus.url"
                ).first()
                if setting:
                    base_url = setting.value

            # 3. 默认值
            if base_url is None:
                base_url = "http://prometheus:9090"

        _prometheus_client = PrometheusClient(base_url=base_url)

    return _prometheus_client
