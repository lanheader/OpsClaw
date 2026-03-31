"""
共享 HTTP 客户端

提供全局共享的 httpx.AsyncClient 实例，支持连接池复用。
"""

import httpx
from typing import Optional
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 全局共享的 HTTP 客户端
_shared_client: Optional[httpx.AsyncClient] = None


def get_shared_http_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """
    获取共享的 HTTP 客户端实例

    使用单例模式，确保所有 HTTP 请求复用同一个连接池。

    Args:
        timeout: 默认超时时间（秒）

    Returns:
        httpx.AsyncClient 实例
    """
    global _shared_client

    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100,
                keepalive_expiry=30.0,
            ),
        )
        logger.debug("🔧 创建共享 HTTP 客户端")

    return _shared_client


async def close_shared_http_client() -> None:
    """
    关闭共享的 HTTP 客户端

    应在应用关闭时调用。
    """
    global _shared_client

    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
        _shared_client = None
        logger.debug("🔌 关闭共享 HTTP 客户端")


__all__ = [
    "get_shared_http_client",
    "close_shared_http_client",
]
