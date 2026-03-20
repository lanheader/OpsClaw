"""
DeepAgents 模块
提供主智能体配置和工厂函数
"""

from .main_agent import get_ops_agent
from .factory import create_agent_for_session

__all__ = [
    "get_ops_agent",
    "create_agent_for_session",
]
