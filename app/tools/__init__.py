"""工具包初始化"""

from . import k8s_tools
from . import prometheus_tools
from . import log_tools
from . import alert_tools
from . import command_executor_tools


def get_k8s_tools():
    """获取所有 K8s 工具"""
    # 返回 k8s_tools 模块中所有带 @tool 装饰器的函数
    tools = []
    for name in dir(k8s_tools):
        if name.startswith("_"):
            continue
        obj = getattr(k8s_tools, name)
        # LangChain tool 是 StructuredTool 类型
        if hasattr(obj, "invoke") and hasattr(obj, "name"):
            tools.append(obj)
    return tools


def get_prometheus_tools():
    """获取所有 Prometheus 工具"""
    tools = []
    for name in dir(prometheus_tools):
        if name.startswith("_"):
            continue
        obj = getattr(prometheus_tools, name)
        if hasattr(obj, "invoke") and hasattr(obj, "name"):
            tools.append(obj)
    return tools


def get_loki_tools():
    """获取所有 Loki 工具"""
    tools = []
    for name in dir(log_tools):
        if name.startswith("_"):
            continue
        obj = getattr(log_tools, name)
        if hasattr(obj, "invoke") and hasattr(obj, "name"):
            tools.append(obj)
    return tools


def get_command_executor_tools():
    """获取所有命令执行工具"""
    tools = []
    for name in dir(command_executor_tools):
        if name.startswith("_"):
            continue
        obj = getattr(command_executor_tools, name)
        if hasattr(obj, "invoke") and hasattr(obj, "name"):
            tools.append(obj)
    return tools


def get_approval_tools():
    """获取所有批准工具"""
    # TODO: 实现批准工具
    return []


def get_all_tools():
    """获取所有工具"""
    tools = []
    tools.extend(get_k8s_tools())
    tools.extend(get_prometheus_tools())
    tools.extend(get_loki_tools())
    tools.extend(get_command_executor_tools())
    tools.extend(get_approval_tools())
    return tools


__all__ = [
    "k8s_tools",
    "prometheus_tools",
    "log_tools",
    "alert_tools",
    "command_executor_tools",
    "get_k8s_tools",
    "get_prometheus_tools",
    "get_loki_tools",
    "get_command_executor_tools",
    "get_approval_tools",
    "get_all_tools",
]
