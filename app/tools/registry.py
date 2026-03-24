"""
工具自动发现和注册系统

负责工具的自动扫描、注册和管理。
支持两级权限控制（分组 + 工具级）。
"""

import importlib
import inspect
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Type, Any
from dataclasses import dataclass, field

from app.tools.base import BaseOpTool, ToolMetadata, ToolCategory, OperationType, RiskLevel

logger = logging.getLogger(__name__)


@dataclass
class ToolGroup:
    """工具分组"""
    code: str  # 分组代码：k8s.read, k8s.write, prometheus.query
    name: str  # 分组名称
    category: ToolCategory  # 所属分类
    operation_type: OperationType  # 操作类型
    description: str  # 分组描述
    tools: Dict[str, Type[BaseOpTool]] = field(default_factory=dict)  # 工具类映射

    def add_tool(self, tool_class: Type[BaseOpTool]):
        """添加工具到分组"""
        metadata = tool_class.get_metadata()
        if metadata:
            self.tools[metadata.name] = tool_class

    def get_tool(self, name: str) -> Optional[Type[BaseOpTool]]:
        """获取工具类"""
        return self.tools.get(name)

    def list_tools(self) -> List[str]:
        """列出所有工具名称"""
        return list(self.tools.keys())

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "code": self.code,
            "name": self.name,
            "category": self.category.value,
            "operation_type": self.operation_type.value,
            "description": self.description,
            "tools": self.list_tools(),
        }


@dataclass
class ToolPermission:
    """工具权限定义"""
    code: str  # 权限代码：k8s.view, k8s.delete
    name: str  # 权限名称
    description: str  # 权限描述
    groups: List[str] = field(default_factory=list)  # 关联的分组代码

    def add_group(self, group_code: str):
        """添加关联分组"""
        if group_code not in self.groups:
            self.groups.append(group_code)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "groups": self.groups,
        }


def _generate_permission_name(perm_code: str) -> str:
    """从权限代码生成友好的权限名称"""
    # 权限代码格式:
    # - system.action (如 k8s.view, k8s.scale)
    # - system.resource_action (如 k8s.delete_pods, k8s.deploy_images)

    parts = perm_code.split('.')

    if len(parts) < 2:
        return perm_code

    system = parts[0].upper()  # k8s -> K8S, prometheus -> PROMETHEUS

    if len(parts) == 2:
        # 格式: system.action (k8s.view, prometheus.query)
        action = parts[1]
        action_map = {
            'view': '查看权限',
            'query': '查询权限',
            'delete': '删除权限',
            'scale': '扩缩容权限',
            'deploy': '部署权限',
            'restart': '重启权限',
            'update': '更新权限',
            'execute': '执行权限',
        }
        return f"{system} {action_map.get(action, action)}"

    # 格式: system.action_resource (k8s.delete_pods, k8s.deploy_images)
    # 注意：动作在前，资源在后
    action_part = parts[1]  # delete, deploy
    resource_part = parts[2] if len(parts) > 2 else ''  # pods, images

    # 动作映射
    action_map = {
        'delete': '删除',
        'deploy': '部署',
        'scale': '扩缩容',
        'restart': '重启',
        'update': '更新',
        'view': '查看',
        'query': '查询',
    }

    # 资源名称映射（复数转单数）
    resource_map = {
        'pods': 'Pod',
        'deployments': 'Deployment',
        'services': 'Service',
        'configmaps': 'ConfigMap',
        'secrets': 'Secret',
        'namespaces': 'Namespace',
        'nodes': 'Node',
        'events': 'Event',
        'images': '镜像',
        'logs': '日志',
        'metrics': '指标',
    }

    action_name = action_map.get(action_part, action_part)
    resource_name = resource_map.get(resource_part, resource_part.title())

    return f"{system} {resource_name}{action_name}"


def _generate_permission_description(perm_code: str) -> str:
    """从权限代码生成权限描述"""
    name = _generate_permission_name(perm_code)

    # 根据系统类型生成不同的描述
    if perm_code.startswith('k8s.'):
        return f"允许{name.replace('K8s ', 'Kubernetes ')}"
    elif perm_code.startswith('prometheus.'):
        return f"允许{name.replace('PROMETHEUS ', 'Prometheus ')}"
    elif perm_code.startswith('loki.'):
        return f"允许{name.replace('LOKI ', 'Loki ')}"
    else:
        return f"允许执行{name}操作"


class ToolRegistry:
    """
    工具注册表

    单例模式，负责工具的自动发现、注册和管理。
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._tool_classes: Dict[str, Type[BaseOpTool]] = {}  # 工具名称 -> 工具类
        self._groups: Dict[str, ToolGroup] = {}  # 分组代码 -> 分组对象
        self._permissions: Dict[str, ToolPermission] = {}  # 权限代码 -> 权限对象

        # 初始化预定义分组
        self._init_predefined_groups()

    def _init_predefined_groups(self):
        """初始化预定义的工具分组"""
        predefined = [
            # K8s 读操作分组
            ToolGroup(
                code="k8s.read",
                name="K8s 读操作",
                category=ToolCategory.K8S,
                operation_type=OperationType.READ,
                description="Kubernetes 资源查询操作（Pod、Deployment、Service 等）"
            ),
            # K8s 写操作分组
            ToolGroup(
                code="k8s.write",
                name="K8s 写操作",
                category=ToolCategory.K8S,
                operation_type=OperationType.WRITE,
                description="Kubernetes 资源创建和更新操作"
            ),
            # K8s 删除操作分组
            ToolGroup(
                code="k8s.delete",
                name="K8s 删除操作",
                category=ToolCategory.K8S,
                operation_type=OperationType.DELETE,
                description="Kubernetes 资源删除操作"
            ),
            # K8s 更新操作分组
            ToolGroup(
                code="k8s.update",
                name="K8s 更新操作",
                category=ToolCategory.K8S,
                operation_type=OperationType.UPDATE,
                description="Kubernetes 资源修改操作（ConfigMap、Secret 等）"
            ),
            # Prometheus 查询分组
            ToolGroup(
                code="prometheus.query",
                name="Prometheus 查询",
                category=ToolCategory.PROMETHEUS,
                operation_type=OperationType.READ,
                description="Prometheus 指标查询操作"
            ),
            # Loki 查询分组
            ToolGroup(
                code="loki.query",
                name="Loki 日志查询",
                category=ToolCategory.LOKI,
                operation_type=OperationType.READ,
                description="Loki 日志查询操作"
            ),
        ]

        for group in predefined:
            self._groups[group.code] = group

    @classmethod
    def register_tool_class(cls, tool_class: Type[BaseOpTool]):
        """注册工具类"""
        registry = cls()
        metadata = tool_class.get_metadata()

        if not metadata:
            logger.warning(f"Tool class {tool_class.__name__} has no metadata")
            return

        # 存储工具类
        registry._tool_classes[metadata.name] = tool_class

        # 添加到分组
        if metadata.group not in registry._groups:
            # 自动创建分组
            from app.tools.base import ToolCategory
            category_str = metadata.group.split('.')[0] if '.' in metadata.group else 'command'
            try:
                category = ToolCategory(category_str)
            except ValueError:
                category = ToolCategory.COMMAND

            registry._groups[metadata.group] = ToolGroup(
                code=metadata.group,
                name=metadata.group.replace('.', ' ').title(),
                category=category,
                operation_type=metadata.operation_type,
                description=f"Auto-generated group for {metadata.group}"
            )

        registry._groups[metadata.group].add_tool(tool_class)

        # 注册权限
        for perm_code in metadata.permissions:
            if perm_code not in registry._permissions:
                # 生成友好的权限名称和描述
                perm_name = _generate_permission_name(perm_code)
                perm_description = _generate_permission_description(perm_code)

                registry._permissions[perm_code] = ToolPermission(
                    code=perm_code,
                    name=perm_name,
                    description=perm_description
                )

            if metadata.group not in registry._permissions[perm_code].groups:
                registry._permissions[perm_code].add_group(metadata.group)

        logger.debug(f"Registered tool: {metadata.name} in group {metadata.group}")

    def scan_and_register(self, tool_packages: List[str] = None):
        """
        扫描并注册所有工具

        Args:
            tool_packages: 要扫描的包列表（默认扫描 k8s, prometheus, loki）
                          支持短格式（如 "k8s"）或完整路径（如 "app.tools.k8s"）
        """
        if tool_packages is None:
            tool_packages = [
                "app.tools.k8s",
                "app.tools.prometheus",
                "app.tools.loki",
                "app.tools.chat",  # 对话历史工具
            ]

        for package in tool_packages:
            try:
                # 支持短格式，自动转换为完整路径
                if not package.startswith("app.tools."):
                    package = f"app.tools.{package}"
                self._scan_package(package)
            except Exception as e:
                logger.error(f"Failed to scan package {package}: {e}")

        logger.info(
            f"Tool registry initialized: {len(self._tool_classes)} tools, "
            f"{len(self._groups)} groups, {len(self._permissions)} permissions"
        )

    def _scan_package(self, package: str):
        """扫描包并注册所有工具类"""
        # 导入包
        module = importlib.import_module(package)

        # 获取包路径
        package_path = Path(module.__file__).parent

        # 扫描所有 Python 文件
        for py_file in package_path.glob("**/*.py"):
            if py_file.name.startswith("_"):
                continue

            # 构建模块路径
            rel_path = py_file.relative_to(package_path)
            module_path = f"{package}.{str(rel_path.with_suffix('')).replace('/', '.')}"

            try:
                # 导入模块
                module = importlib.import_module(module_path)

                # 查找所有工具类
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseOpTool) and obj != BaseOpTool:
                        self.register_tool_class(obj)

            except ImportError as e:
                logger.debug(f"Cannot import {module_path}: {e}")

    def get_group(self, code: str) -> Optional[ToolGroup]:
        """获取工具分组"""
        return self._groups.get(code)

    def list_groups(self) -> List[ToolGroup]:
        """列出所有工具分组"""
        return list(self._groups.values())

    def get_tool(self, name: str) -> Optional[Type[BaseOpTool]]:
        """获取工具类"""
        return self._tool_classes.get(name)

    def list_tools(self, group_code: str = None) -> List[Type[BaseOpTool]]:
        """列出工具类"""
        if group_code:
            group = self.get_group(group_code)
            return list(group.tools.values()) if group else []
        return list(self._tool_classes.values())

    def get_permissions(self) -> List[ToolPermission]:
        """获取所有权限定义"""
        return list(self._permissions.values())

    def get_langchain_tools(
        self,
        group_code: str = None,
        package: str = None,
        permissions: Set[str] = None,
        user_id: Optional[int] = None,
        db = None
    ) -> List[Any]:
        """
        获取 LangChain 工具列表

        Args:
            group_code: 工具分组代码（可选）
            package: 包名（可选，如 "k8s", "prometheus", "loki"）
            permissions: 用户权限集合（可选，用于过滤）
            user_id: 用户ID（可选，用于动态获取权限）
            db: 数据库会话（可选，用于动态获取权限）

        Returns:
            LangChain 工具列表
        """
        # 如果提供了 user_id 和 db，动态获取权限
        if permissions is None and user_id is not None and db is not None:
            from app.core.permission_checker import get_user_permission_codes
            permissions = set(get_user_permission_codes(db, user_id))

        tools = []

        for tool_class in self.list_tools(group_code):
            metadata = tool_class.get_metadata()

            if not metadata:
                continue

            # 检查是否启用
            if not metadata.enabled:
                continue

            # 检查是否暴露给 agent
            if not metadata.expose_to_agent:
                continue

            # 按包过滤
            if package is not None:
                tool_package = metadata.group.split('.')[0] if metadata.group else ''
                if tool_package != package:
                    continue

            # 检查权限
            if permissions is not None:
                required_perms = set(metadata.permissions)
                if not required_perms:
                    # 无权限要求，默认允许
                    pass
                elif not required_perms.issubset(permissions):
                    continue

            # 创建 LangChain 工具
            try:
                lc_tool = tool_class.get_langchain_tool()
                tools.append(lc_tool)
            except Exception as e:
                logger.error(f"Failed to create LangChain tool for {metadata.name}: {e}")

        return tools


# 全局实例
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """获取工具注册表单例"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _registry.scan_and_register()
    return _registry


__all__ = [
    "ToolGroup",
    "ToolPermission",
    "ToolRegistry",
    "get_tool_registry",
]
