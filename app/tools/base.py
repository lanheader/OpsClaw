"""
工具基类和装饰器

定义统一的工具规范，支持工具自动发现和权限声明。
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, List, Set
from functools import wraps
import logging

logger = logging.getLogger(__name__)


class ToolCategory(str, Enum):
    """工具分类"""
    K8S = "k8s"
    PROMETHEUS = "prometheus"
    LOKI = "loki"
    COMMAND = "command"  # 内部降级使用，不暴露给 agent


class OperationType(str, Enum):
    """操作类型"""
    READ = "read"
    WRITE = "write"
    UPDATE = "update"
    DELETE = "delete"


class RiskLevel(str, Enum):
    """风险等级"""
    LOW = "low"        # 只读操作，无风险
    MEDIUM = "medium"  # 可能影响系统性能
    HIGH = "high"      # 可能造成数据丢失或服务中断


class ToolMetadata:
    """工具元数据"""

    def __init__(
        self,
        group: str,                    # 工具分组：k8s.read, k8s.write, prometheus.query
        name: str,                     # 工具名称
        operation_type: OperationType,
        risk_level: RiskLevel,
        permissions: List[str],        # 所需权限列表
        description: str,
        examples: List[str] = None,
        enabled: bool = True,
        expose_to_agent: bool = True,  # 是否暴露给 agent
    ):
        self.group = group
        self.name = name
        self.operation_type = operation_type
        self.risk_level = risk_level
        self.permissions = permissions
        self.description = description
        self.examples = examples or []
        self.enabled = enabled
        self.expose_to_agent = expose_to_agent

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "group": self.group,
            "name": self.name,
            "operation_type": self.operation_type.value,
            "risk_level": self.risk_level.value,
            "permissions": self.permissions,
            "description": self.description,
            "examples": self.examples,
            "enabled": self.enabled,
            "expose_to_agent": self.expose_to_agent,
        }


class BaseOpTool(ABC):
    """
    工具基类

    所有工具类都需要继承此类，并使用 @register_tool 装饰器。
    """

    # 类级别的元数据，由 @register_tool 装饰器设置
    _metadata: Optional[ToolMetadata] = None

    @classmethod
    def get_metadata(cls) -> Optional[ToolMetadata]:
        """获取工具元数据"""
        return cls._metadata

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行工具操作

        Returns:
            {
                "success": bool,
                "data": Any,
                "error": str (可选),
                "execution_mode": "sdk" | "cli",
                "source": str (数据源标识)
            }
        """
        pass

    @classmethod
    def get_langchain_tool(cls):
        """获取 LangChain 工具对象"""
        if not cls._metadata:
            raise ValueError(f"Tool {cls.__name__} not registered")

        from langchain_core.tools import tool

        metadata = cls._metadata

        # 使用 description 参数创建工具
        @tool(description=metadata.description)
        async def langchain_tool(**kwargs):
            instance = cls()
            return await instance.execute(**kwargs)

        # 设置 LangChain 工具的元数据
        langchain_tool.name = metadata.name
        langchain_tool._op_tool_metadata = metadata
        langchain_tool._op_tool_class = cls

        return langchain_tool


def register_tool(
    group: str,
    operation_type: OperationType,
    risk_level: RiskLevel,
    permissions: List[str],
    description: str,
    examples: List[str] = None,
    enabled: bool = True,
    expose_to_agent: bool = True,
):
    """
    工具注册装饰器

    用法：
        @register_tool(
            group="k8s.read",
            operation_type=OperationType.READ,
            risk_level=RiskLevel.LOW,
            permissions=["k8s.view"],
            description="获取 Kubernetes Pod 列表",
            examples=[
                "get_pods_tool(namespace='default')",
                "get_pods_tool(namespace='production', label_selector='app=api')"
            ]
        )
        class GetPodsTool(BaseOpTool):
            async def execute(self, namespace: str = "default", **kwargs):
                ...
    """
    def decorator(cls):
        # 提取工具名称（去掉 Tool 后缀）
        name = cls.__name__
        if name.endswith("Tool"):
            name = name[:-4]
        # 转换为 snake_case
        import re
        name = re.sub('(?<!^)(?=[A-Z])', '_', name).lower()

        # 创建元数据
        metadata = ToolMetadata(
            group=group,
            name=name,
            operation_type=operation_type,
            risk_level=risk_level,
            permissions=permissions,
            description=description,
            examples=examples,
            enabled=enabled,
            expose_to_agent=expose_to_agent,
        )

        # 设置类级别元数据
        cls._metadata = metadata

        # 自动注册到工具注册表
        from app.tools.registry import ToolRegistry
        ToolRegistry.register_tool_class(cls)

        logger.debug(f"Registered tool: {name} in group {group}")

        return cls

    return decorator


def get_tool_permissions(tool) -> List[str]:
    """
    从工具对象提取权限要求

    Args:
        tool: LangChain 工具对象或 BaseOpTool 实例

    Returns:
        权限代码列表
    """
    # 如果是 LangChain 工具对象
    if hasattr(tool, '_op_tool_metadata'):
        return tool._op_tool_metadata.permissions

    # 如果是 BaseOpTool 类
    if isinstance(tool, type) and issubclass(tool, BaseOpTool):
        metadata = tool.get_metadata()
        if metadata:
            return metadata.permissions

    return []


__all__ = [
    "ToolCategory",
    "OperationType",
    "RiskLevel",
    "ToolMetadata",
    "BaseOpTool",
    "register_tool",
    "get_tool_permissions",
]
