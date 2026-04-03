"""
Uvicorn 日志配置 - 统一使用 Loguru

将 uvicorn 的所有日志（access、error、default）都重定向到 Loguru
"""

import logging
import sys
from typing import Any, Dict

# Uvicorn 日志配置字典
# 这个配置会完全替换 uvicorn 的默认日志系统
LOGGING_CONFIG: Dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "default": {
            "class": "app.utils.loguru_config.InterceptHandler",
        },
        "access": {
            "class": "app.utils.loguru_config.InterceptHandler",
        },
    },
    "loggers": {
        "uvicorn": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["access"],
            "level": "INFO",
            "propagate": False,
        },
    },
}


def get_uvicorn_log_config() -> Dict[str, Any]:
    """获取 uvicorn 日志配置"""
    return LOGGING_CONFIG
