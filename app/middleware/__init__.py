"""
中间件注册和管理

DeepAgents 中间件系统

实际使用的中间件（必须继承 langchain.agents.middleware.types.AgentMiddleware）：
- LoggingMiddleware: 记录 LLM 和工具调用
- ErrorFilteringMiddleware: 过滤错误信息
- DynamicPermissionMiddleware: 动态权限检查（运行时）
- DynamicApprovalMiddleware: 动态审批检查（运行时）

已移除：
- MessageTrimmingMiddleware: 被 deepagents 内置 SummarizationMiddleware 替代
"""

from .logging_middleware import LoggingMiddleware
from .error_filtering_middleware import ErrorFilteringMiddleware
from .dynamic_permission_middleware import DynamicPermissionMiddleware
from .dynamic_approval_middleware import DynamicApprovalMiddleware

__all__ = [
    "LoggingMiddleware",
    "ErrorFilteringMiddleware",
    "DynamicPermissionMiddleware",
    "DynamicApprovalMiddleware",
]
