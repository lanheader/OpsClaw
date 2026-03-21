"""
中间件注册和管理

DeepAgents 中间件系统

实际使用的中间件（必须继承 langchain_core.agent.AgentMiddleware）：
- LoggingMiddleware: 记录 LLM 和工具调用
- MessageTrimmingMiddleware: 截断消息历史防止 token 溢出

注意：已删除的中间件（使用自定义 BaseMiddleware，与 DeepAgents 不兼容）：
- ApprovalMiddleware: DeepAgents 使用 interrupt_on 机制实现批准流程
- RoutingMiddleware: 路由功能已被主智能体吸收
- SecurityMiddleware: 使用静态权限过滤即可
- BaseMiddleware: 自定义基类，不兼容 DeepAgents
"""

from .logging_middleware import LoggingMiddleware
from .message_trimming_middleware import MessageTrimmingMiddleware

__all__ = [
    "LoggingMiddleware",
    "MessageTrimmingMiddleware",
]
