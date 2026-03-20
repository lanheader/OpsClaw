"""工具注册表 - 统一管理 SDK 和 CLI 工具

提供：
- 工具注册和查找
- SDK 和 CLI 工具的映射关系
- 统一的工具获取接口
"""

from typing import Dict, Any, Optional, Callable, List
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ToolType(Enum):
    """工具类型"""

    SDK = "sdk"  # SDK 工具（如 Kubernetes Python 客户端）
    CLI = "cli"  # 命令行工具（如 kubectl）


class ToolInfo:
    """工具信息"""

    def __init__(
        self,
        name: str,
        tool_type: ToolType,
        func: Callable,
        description: str,
        category: str,
        fallback_tool: Optional[str] = None,
        param_mapping: Optional[Dict[str, str]] = None,
    ):
        """
        初始化工具信息

        Args:
            name: 工具名称
            tool_type: 工具类型（SDK 或 CLI）
            func: 工具函数
            description: 工具描述
            category: 工具分类（k8s, redis, mysql, prometheus, loki 等）
            fallback_tool: 降级工具名称（仅 SDK 工具需要）
            param_mapping: 参数映射（SDK 参数 -> CLI 参数）
        """
        self.name = name
        self.tool_type = tool_type
        self.func = func
        self.description = description
        self.category = category
        self.fallback_tool = fallback_tool
        self.param_mapping = param_mapping or {}

    def __repr__(self) -> str:
        return f"ToolInfo(name={self.name}, type={self.tool_type.value}, category={self.category})"


class ToolRegistry:
    """
    工具注册表

    统一管理所有 SDK 和 CLI 工具，提供：
    - 工具注册
    - 工具查找
    - 降级工具映射
    - 按分类获取工具
    """

    def __init__(self):
        # 工具存储：{tool_name: ToolInfo}
        self._tools: Dict[str, ToolInfo] = {}

        # 分类索引：{category: [tool_name, ...]}
        self._category_index: Dict[str, List[str]] = {}

        # 类型索引：{tool_type: [tool_name, ...]}
        self._type_index: Dict[ToolType, List[str]] = {ToolType.SDK: [], ToolType.CLI: []}

    def register(
        self,
        name: str,
        tool_type: ToolType,
        func: Callable,
        description: str,
        category: str,
        fallback_tool: Optional[str] = None,
        param_mapping: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        注册工具

        Args:
            name: 工具名称
            tool_type: 工具类型
            func: 工具函数
            description: 工具描述
            category: 工具分类
            fallback_tool: 降级工具名称
            param_mapping: 参数映射
        """
        if name in self._tools:
            logger.warning(f"工具 {name} 已存在，将被覆盖")

        tool_info = ToolInfo(
            name=name,
            tool_type=tool_type,
            func=func,
            description=description,
            category=category,
            fallback_tool=fallback_tool,
            param_mapping=param_mapping,
        )

        # 存储工具
        self._tools[name] = tool_info

        # 更新分类索引
        if category not in self._category_index:
            self._category_index[category] = []
        if name not in self._category_index[category]:
            self._category_index[category].append(name)

        # 更新类型索引
        if name not in self._type_index[tool_type]:
            self._type_index[tool_type].append(name)

        logger.info(f"注册工具: {name} ({tool_type.value}, {category})")

    def get_tool(self, name: str) -> Optional[ToolInfo]:
        """
        获取工具信息

        Args:
            name: 工具名称

        Returns:
            工具信息，如果不存在返回 None
        """
        return self._tools.get(name)

    def get_tool_func(self, name: str) -> Optional[Callable]:
        """
        获取工具函数

        Args:
            name: 工具名称

        Returns:
            工具函数，如果不存在返回 None
        """
        tool_info = self.get_tool(name)
        return tool_info.func if tool_info else None

    def get_fallback_tool(self, sdk_tool_name: str) -> Optional[ToolInfo]:
        """
        获取降级工具

        Args:
            sdk_tool_name: SDK 工具名称

        Returns:
            降级工具信息，如果不存在返回 None
        """
        sdk_tool = self.get_tool(sdk_tool_name)
        if not sdk_tool or not sdk_tool.fallback_tool:
            return None

        return self.get_tool(sdk_tool.fallback_tool)

    def get_tools_by_category(self, category: str) -> List[ToolInfo]:
        """
        按分类获取工具

        Args:
            category: 工具分类

        Returns:
            工具信息列表
        """
        tool_names = self._category_index.get(category, [])
        return [self._tools[name] for name in tool_names]

    def get_tools_by_type(self, tool_type: ToolType) -> List[ToolInfo]:
        """
        按类型获取工具

        Args:
            tool_type: 工具类型

        Returns:
            工具信息列表
        """
        tool_names = self._type_index.get(tool_type, [])
        return [self._tools[name] for name in tool_names]

    def get_sdk_tools(self) -> List[ToolInfo]:
        """获取所有 SDK 工具"""
        return self.get_tools_by_type(ToolType.SDK)

    def get_cli_tools(self) -> List[ToolInfo]:
        """获取所有 CLI 工具"""
        return self.get_tools_by_type(ToolType.CLI)

    def list_tools(self) -> List[ToolInfo]:
        """列出所有工具"""
        return list(self._tools.values())

    def list_categories(self) -> List[str]:
        """列出所有分类"""
        return list(self._category_index.keys())

    def get_tool_mapping(self) -> Dict[str, str]:
        """
        获取 SDK 工具到 CLI 工具的映射

        Returns:
            {sdk_tool_name: cli_tool_name}
        """
        mapping = {}
        for tool_info in self.get_sdk_tools():
            if tool_info.fallback_tool:
                mapping[tool_info.name] = tool_info.fallback_tool
        return mapping

    def __len__(self) -> int:
        """返回工具数量"""
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        """检查工具是否存在"""
        return name in self._tools

    def __repr__(self) -> str:
        sdk_count = len(self._type_index[ToolType.SDK])
        cli_count = len(self._type_index[ToolType.CLI])
        return f"ToolRegistry(total={len(self)}, sdk={sdk_count}, cli={cli_count})"


# 全局工具注册表实例
_global_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    """获取全局工具注册表"""
    return _global_registry


def register_tool(
    name: str,
    tool_type: ToolType,
    func: Callable,
    description: str,
    category: str,
    fallback_tool: Optional[str] = None,
    param_mapping: Optional[Dict[str, str]] = None,
) -> None:
    """
    注册工具到全局注册表

    Args:
        name: 工具名称
        tool_type: 工具类型
        func: 工具函数
        description: 工具描述
        category: 工具分类
        fallback_tool: 降级工具名称
        param_mapping: 参数映射
    """
    _global_registry.register(
        name=name,
        tool_type=tool_type,
        func=func,
        description=description,
        category=category,
        fallback_tool=fallback_tool,
        param_mapping=param_mapping,
    )


def get_tool(name: str) -> Optional[ToolInfo]:
    """从全局注册表获取工具"""
    return _global_registry.get_tool(name)


def get_tool_func(name: str) -> Optional[Callable]:
    """从全局注册表获取工具函数"""
    return _global_registry.get_tool_func(name)


def get_fallback_tool(sdk_tool_name: str) -> Optional[ToolInfo]:
    """从全局注册表获取降级工具"""
    return _global_registry.get_fallback_tool(sdk_tool_name)
