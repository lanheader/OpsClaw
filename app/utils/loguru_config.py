"""
Loguru 日志配置

使用 loguru 替代标准 logging 模块

Loguru 优势：
- 开箱即用，无需复杂配置
- 自动捕获异常和回溯
- 内置日志轮转和压缩
- 更好的颜色化和格式化
- 支持 coroutined 和 async
"""

import logging
import sys
from pathlib import Path
from loguru import logger

# 移除默认的 handler
logger.remove()

# 添加控制台输出（带颜色）
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
    level="INFO",
    colorize=True,
    backtrace=True,
    diagnose=True,
)

# 添加文件输出（自动轮转）
log_dir = Path("./logs")
log_dir.mkdir(exist_ok=True)

# 一般日志文件
logger.add(
    log_dir / "app.log",
    rotation="500 MB",  # 文件达到 500MB 时轮转
    retention="30 days",  # 保留 30 天
    compression="zip",  # 压缩旧日志
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    backtrace=True,
    diagnose=True,
)

# 错误日志文件（单独记录）
logger.add(
    log_dir / "error.log",
    rotation="100 MB",
    retention="90 days",
    compression="zip",
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    backtrace=True,
    diagnose=True,
)

# 捕获标准库 logging 的日志并转发到 loguru


class InterceptHandler(logging.Handler):
    """拦截标准 logging 并转发到 loguru"""

    def emit(self, record):
        # 获取对应的 loguru level
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 查找调用者
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        # 对于 uvicorn.access 日志，格式化请求信息
        if record.name == "uvicorn.access":
            # uvicorn access log 格式: '172.24.39.12:0 - "POST /api/v1/... HTTP/1.1" 200 OK'
            msg = record.getMessage()
            try:
                # 提取请求方法和路径
                if '"' in msg:
                    parts = msg.split('"')
                    if len(parts) >= 3:
                        request_info = parts[1].strip()  # "POST /api/v1/... HTTP/1.1"
                        status_info = parts[2].strip()   # "200 OK"
                        request_parts = request_info.split()
                        if len(request_parts) >= 2:
                            method = request_parts[0]
                            path = request_parts[1]
                            logger.opt(depth=depth, exception=record.exc_info).log(
                                level, "HTTP {} {} {}", method, path, status_info
                            )
                            return
            except Exception:
                pass

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


# 配置第三方库的日志级别
LOGGING_LEVELS = {
    "uvicorn": "INFO",
    "uvicorn.access": "INFO",
    "uvicorn.error": "INFO",
    "fastapi": "INFO",
    "langchain": "WARNING",
    "langgraph": "WARNING",
    "httpx": "WARNING",
    "httpcore": "WARNING",
    "openai": "WARNING",
    "anthropic": "WARNING",
    "sqlalchemy": "WARNING",
    "alembic": "WARNING",
    # 抑制 LiteLLM 的 DEBUG 日志
    "litellm": "WARNING",
    "litellm_logging": "WARNING",
    # 抑制内部模块的 DEBUG 日志
    "app.tools.base": "INFO",
    "app.tools": "INFO",
}


def setup_logging():
    """配置日志系统"""
    # 拦截标准库的 logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # 配置第三方库的日志级别
    for name, level in LOGGING_LEVELS.items():
        logging_logger = logging.getLogger(name)
        logging_logger.setLevel(level)
        # 确保 uvicorn 使用我们的 handler
        logging_logger.handlers = [InterceptHandler()]

    logger.info("✅ Loguru 日志系统初始化完成")


__all__ = ["logger", "setup_logging"]
