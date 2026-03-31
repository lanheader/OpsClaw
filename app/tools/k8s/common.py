"""
K8s 工具公共函数

提供 K8s 工具共用的初始化和日志函数。
"""

from typing import Optional

from app.integrations.kubernetes.client import create_client
from app.utils.logger import get_logger, get_request_context

logger = get_logger(__name__)


def init_k8s_client(db=None):
    """初始化 K8s 客户端"""
    return create_client(db)


def log_tool_start(tool_name: str, **kwargs):
    """记录工具开始执行的日志"""
    ctx = get_request_context()
    session_id = ctx.get('session_id', 'no-sess')
    params = {k: v for k, v in kwargs.items() if v is not None}
    logger.info(f"🔧 [{session_id}] 执行工具: {tool_name} | 参数: {params}")


def log_tool_success(tool_name: str, result_count: int = None):
    """记录工具执行成功的日志"""
    ctx = get_request_context()
    session_id = ctx.get('session_id', 'no-sess')
    if result_count is not None:
        logger.info(f"✅ [{session_id}] 工具完成: {tool_name} | 返回 {result_count} 条记录")
    else:
        logger.info(f"✅ [{session_id}] 工具完成: {tool_name}")


def is_pod_ready(pod) -> str:
    """检查 Pod 是否就绪"""
    if not pod.status.container_statuses:
        return "0/0"
    ready = sum(1 for c in pod.status.container_statuses if c.ready)
    total = len(pod.status.container_statuses)
    return f"{ready}/{total}"


def format_timestamp(timestamp) -> Optional[str]:
    """格式化时间戳为 ISO 格式"""
    if timestamp:
        return timestamp.isoformat()
    return None


__all__ = [
    "init_k8s_client",
    "log_tool_start",
    "log_tool_success",
    "is_pod_ready",
    "format_timestamp",
]
