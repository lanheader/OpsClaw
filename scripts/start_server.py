#!/usr/bin/env python3
"""
启动 Ops Agent 服务器
使用 .env 配置文件中的 HOST、PORT、RELOAD 等配置
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import uvicorn
from app.core.config import get_settings


def main():
    """启动服务器"""
    settings = get_settings()

    print(f"🚀 启动 Ops Agent 服务器...")
    print(f"📍 地址: http://{settings.HOST}:{settings.PORT}")
    print(f"📖 API 文档: http://{settings.HOST}:{settings.PORT}/docs (ENABLE_DOCS={settings.ENABLE_DOCS})")
    print(f"🔄 热重载: {settings.RELOAD}")
    print(f"🌐 CORS: {settings.ENABLE_CORS}")
    print(f"📝 日志级别: {settings.LOG_LEVEL}")
    print()

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
