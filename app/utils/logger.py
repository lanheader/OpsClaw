"""日志工具模块 - 支持请求追踪"""

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Optional, Dict, Any

# 请求上下文 - 用于跨异步调用传递 request_id 和 session_id
_request_context: ContextVar[Dict[str, Any]] = ContextVar('request_context', default={})


def set_request_context(session_id: str, request_id: str = None, user_id: str = None, channel: str = None) -> str:
    """
    设置当前请求的上下文信息

    Args:
        session_id: 会话 ID
        request_id: 请求 ID（可选，不传则自动生成）
        user_id: 用户 ID（可选）
        channel: 渠道（web/feishu，可选）

    Returns:
        生成的 request_id
    """
    request_id = request_id or generate_request_id()
    ctx = {
        'session_id': session_id,
        'request_id': request_id,
        'user_id': user_id,
        'channel': channel,
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


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    获取日志记录器

    Args:
        name: 日志记录器名称，通常传入 __name__

    Returns:
        配置好的 Logger 实例
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
