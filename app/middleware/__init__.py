"""
中间件注册和管理

DeepAgents 中间件系统

实际使用的中间件（必须继承 langchain.agents.middleware.types.AgentMiddleware）：
- LoggingMiddleware: 记录 LLM 和工具调用
- StoreMemoryMiddleware: 从知识库动态注入相关知识到 system_prompt
"""

from .logging_middleware import LoggingMiddleware
from .store_memory_middleware import StoreMemoryMiddleware

__all__ = [
    "LoggingMiddleware",
    "StoreMemoryMiddleware",
]
