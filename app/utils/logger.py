"""日志工具模块 - 支持请求追踪 + Loguru 集成"""

import json
import logging
import sys
import uuid
import os
from contextvars import ContextVar
from typing import Optional, Dict, Any, Union

# 尝试导入 loguru，如果可用则使用 loguru
try:
    from loguru import logger as _loguru_logger
    LOGURU_AVAILABLE = True
except ImportError:
    LOGURU_AVAILABLE = False
    _loguru_logger = None

# 请求上下文 - 用于跨异步调用传递 request_id 和 session_id
_request_context: ContextVar[Dict[str, Any]] = ContextVar('request_context', default={})

# 环境变量控制是否使用 loguru（默认使用 loguru）
USE_LOGURU = os.getenv("USE_LOGURU", "true").lower() == "true"


def set_request_context(
    session_id: str,
    request_id: str = None,
    user_id: str = None,
    channel: str = None,
    user_permissions: list = None,
) -> str:
    """
    设置当前请求的上下文信息

    Args:
        session_id: 会话 ID
        request_id: 请求 ID（可选，不传则自动生成）
        user_id: 用户 ID（可选）
        channel: 渠道（web/feishu，可选）
        user_permissions: 用户权限列表（可选，供 middleware 使用）

    Returns:
        生成的 request_id
    """
    request_id = request_id or generate_request_id()
    ctx = {
        'session_id': session_id,
        'request_id': request_id,
        'user_id': user_id,
        'channel': channel,
        'user_permissions': user_permissions or [],
    }
    _request_context.set(ctx)
    return request_id


def clear_request_context():
    """清除当前请求的上下文"""
    _request_context.set({})


def get_request_context() -> Dict[str, Any]:
    """获取当前请求的上下文"""
    return _request_context.get()


def get_request_id() -> str:
    """获取当前请求的 request_id"""
    return _request_context.get().get('request_id', 'no-req')


def get_session_id() -> str:
    """获取当前请求的 session_id"""
    return _request_context.get().get('session_id', 'no-sess')


def generate_request_id() -> str:
    """生成短格式的 request_id（8位）"""
    return str(uuid.uuid4())[:8]


class RequestContextFilter(logging.Filter):
    """
    日志过滤器 - 自动注入 request_id 和 session_id 到日志记录中
    """

    def filter(self, record):
        ctx = _request_context.get()
        record.request_id = ctx.get('request_id', 'no-req')
        record.session_id = ctx.get('session_id', 'no-sess')
        record.user_id = ctx.get('user_id', '-')
        record.channel = ctx.get('channel', '-')
        return True


class ContextFormatter(logging.Formatter):
    """
    自定义日志格式化器 - 支持请求上下文

    格式: 时间 - [会话ID] - [请求ID] - 模块名 - 级别 - 消息
    """

    def format(self, record):
        # 确保上下文字段存在
        if not hasattr(record, 'request_id'):
            record.request_id = 'no-req'
        if not hasattr(record, 'session_id'):
            record.session_id = 'no-sess'

        return super().format(record)


def _suppress_third_party_logs():
    """
    抑制第三方库的冗余日志

    将常见的第三方库日志级别设置为 WARNING，避免 DEBUG/INFO 级别的噪音
    """
    # 需要抑制的第三方库列表
    third_party_loggers = [
        # HTTP 相关
        'openai', 'openai._base_client', 'openai._client',
        'httpx', 'httpcore', 'http.client',
        # LangChain 相关
        'langchain', 'langchain_core', 'langchain_community',
        'langsmith', 'langgraph',
        # 其他常见库
        'urllib3', 'requests', 'aiohttp',
        'asyncio', 'multipart', 'watchfiles',
        # Kubernetes
        'kubernetes', 'kubernetes.client',
    ]

    for logger_name in third_party_loggers:
        third_party_logger = logging.getLogger(logger_name)
        third_party_logger.setLevel(logging.WARNING)
        third_party_logger.propagate = False


# 模块加载时执行一次
_suppress_third_party_logs()


def get_logger(name: Optional[str] = None) -> Union[logging.Logger, Any]:
    """
    获取日志记录器

    根据 USE_LOGURU 环境变量自动选择使用 loguru 或标准 logging

    Args:
        name: 日志记录器名称，通常传入 __name__

    Returns:
        配置好的 Logger 实例（loguru 或 logging）
    """
    # 如果启用了 loguru 且可用，返回 loguru logger
    if USE_LOGURU and LOGURU_AVAILABLE:
        # loguru 的 logger 是全局单例，直接返回
        # 使用 bind() 注入模块名称
        return _loguru_logger.bind(name=name or __name__)

    # 否则使用标准 logging
    return _get_standard_logger(name or __name__)


def _get_standard_logger(name: Optional[str] = None) -> logging.Logger:
    """
    获取标准 logging.Logger（内部函数）

    Args:
        name: 日志记录器名称，通常传入 __name__

    Returns:
        配置好的标准 Logger 实例
    """
    logger = logging.getLogger(name or __name__)

    # 如果已经配置过 handler，直接返回
    if logger.handlers:
        return logger

    # 设置日志级别
    logger.setLevel(logging.DEBUG)  # 允许所有级别，由 handler 控制输出

    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # 添加上下文过滤器
    context_filter = RequestContextFilter()
    console_handler.addFilter(context_filter)

    # 创建格式化器 - 包含 session_id 和 request_id
    formatter = ContextFormatter(
        "%(asctime)s - [%(session_id)s] - [%(request_id)s] - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)

    # 添加处理器
    logger.addHandler(console_handler)

    # 防止日志向上传播到 root logger
    logger.propagate = False

    return logger


# 向后兼容：提供一个全局 logger 实例
def logger(__name__: Optional[str] = None) -> Union[logging.Logger, Any]:
    """便捷函数：直接获取 logger"""
    return get_logger(__name__)


def log_with_context(logger: logging.Logger, level: int, message: str, **kwargs):
    """
    带上下文的日志记录

    Args:
        logger: 日志记录器
        level: 日志级别
        message: 日志消息
        **kwargs: 额外的上下文信息
    """
    ctx = _request_context.get()
    extra_info = " | ".join(f"{k}={v}" for k, v in kwargs.items() if v is not None)
    if extra_info:
        message = f"{message} | {extra_info}"
    logger.log(level, message)


# 便捷函数
def log_tool_call(logger: logging.Logger, tool_name: str, action: str, success: bool = True, **kwargs):
    """
    记录工具调用的便捷函数

    Args:
        logger: 日志记录器
        tool_name: 工具名称
        action: 操作描述
        success: 是否成功
        **kwargs: 额外参数
    """
    status = "✅" if success else "❌"
    ctx = _request_context.get()
    session_id = ctx.get('session_id', 'no-sess')
    request_id = ctx.get('request_id', 'no-req')

    params_str = " | ".join(f"{k}={v}" for k, v in kwargs.items() if v is not None)
    log_msg = f"[{session_id}] [{request_id}] {status} 工具调用: {tool_name} - {action}"
    if params_str:
        log_msg += f" | {params_str}"

    if success:
        logger.info(log_msg)
    else:
        logger.error(log_msg)


def log_agent_call(logger: logging.Logger, agent_name: str, action: str, success: bool = True, **kwargs):
    """
    记录 Agent 调用的便捷函数

    Args:
        logger: 日志记录器
        agent_name: Agent 名称
        action: 操作描述
        success: 是否成功
        **kwargs: 额外参数
    """
    status = "✅" if success else "❌"
    ctx = _request_context.get()
    session_id = ctx.get('session_id', 'no-sess')
    request_id = ctx.get('request_id', 'no-req')

    params_str = " | ".join(f"{k}={v}" for k, v in kwargs.items() if v is not None)
    log_msg = f"[{session_id}] [{request_id}] {status} Agent调用: {agent_name} - {action}"
    if params_str:
        log_msg += f" | {params_str}"

    if success:
        logger.info(log_msg)
    else:
        logger.error(log_msg)


def truncate_for_log(data: Any, max_length: int = 200, max_depth: int = 2) -> str:
    """
    截断数据用于日志输出，避免日志过长

    Args:
        data: 要截断的数据（可以是字符串、字典、列表等）
        max_length: 单个字段的最大长度
        max_depth: 嵌套结构的最大深度

    Returns:
        截断后的字符串表示
    """

    def _truncate(obj: Any, depth: int = 0) -> Any:
        if depth > max_depth:
            return "..."

        if obj is None:
            return None

        if isinstance(obj, str):
            if len(obj) > max_length:
                return obj[:max_length] + f"... ({len(obj)} chars total)"
            return obj

        if isinstance(obj, (int, float, bool)):
            return obj

        if isinstance(obj, dict):
            if len(obj) > 10:
                # 字典太大时只显示键
                return f"<dict with {len(obj)} keys: {list(obj.keys())[:5]}...>"
            return {k: _truncate(v, depth + 1) for k, v in obj.items()}

        if isinstance(obj, (list, tuple)):
            if len(obj) > 5:
                # 列表太长时只显示前几个
                return [_truncate(item, depth + 1) for item in obj[:3]] + [f"... ({len(obj)} items total)"]
            return [_truncate(item, depth + 1) for item in obj]

        # 其他类型，尝试转为字符串
        try:
            s = str(obj)
            if len(s) > max_length:
                return s[:max_length] + f"... ({len(s)} chars total)"
            return s
        except Exception:
            return f"<{type(obj).__name__}>"

    try:
        truncated = _truncate(data)
        return json.dumps(truncated, ensure_ascii=False, default=str)
    except Exception:
        return str(data)[:max_length] + "..."


__all__ = [
    # 配置
    "USE_LOGURU",
    "LOGURU_AVAILABLE",
    # 上下文管理
    "set_request_context",
    "clear_request_context",
    "get_request_context",
    "get_request_id",
    "get_session_id",
    "generate_request_id",
    # 日志组件
    "RequestContextFilter",
    "ContextFormatter",
    "get_logger",
    "logger",
    # 便捷日志函数
    "log_with_context",
    "log_tool_call",
    "log_agent_call",
    # 工具函数
    "truncate_for_log",
]
