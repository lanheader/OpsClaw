"""
工具包初始化

使用 ToolRegistry 统一管理所有工具。

新架构支持：
- 自动发现和注册
- 两级权限控制（分组 + 工具级）
- SDK → CLI 降级机制

📚 扩展工具请参考：app/tools/EXTENSION_GUIDE.md
"""

import logging
from typing import List, Any, Set, Optional
from sqlalchemy.orm import Session

from app.tools.registry import get_tool_registry

logger = logging.getLogger(__name__)


def get_all_tools(
    permissions: Optional[Set[str]] = None,
    user_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> List[Any]:
    """
    获取所有已启用的工具

    Args:
        permissions: 用户权限集合（可选）
        user_id: 用户 ID（可选，用于动态获取权限）
        db: 数据库会话（可选，用于动态获取权限）

    Returns:
        LangChain 工具列表
    """
    registry = get_tool_registry()

    # 如果提供了 user_id 和 db，动态获取权限
    if permissions is None and user_id is not None and db is not None:
        return registry.get_langchain_tools(user_id=user_id, db=db)

    # 否则使用传入的权限或无权限过滤
    return registry.get_langchain_tools(permissions=permissions)  # type: ignore[arg-type]


def get_tools_by_group(
    group_code: str,
    permissions: Optional[Set[str]] = None,
    user_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> List[Any]:
    """
    获取指定分组的工具

    Args:
        group_code: 工具分组代码（如 "k8s.read", "prometheus.query"）
        permissions: 用户权限集合（可选）
        user_id: 用户 ID（可选，用于动态获取权限）
        db: 数据库会话（可选，用于集成开关检查）

    Returns:
        LangChain 工具列表
    """
    registry = get_tool_registry()

    # 如果提供了 user_id 和 db，动态获取权限
    if permissions is None and user_id is not None and db is not None:
        return registry.get_langchain_tools(group_code=group_code, user_id=user_id, db=db)

    return registry.get_langchain_tools(group_code=group_code, permissions=permissions, db=db)  # type: ignore[arg-type]


def list_groups() -> List[dict]:
    """
    列出所有工具分组

    Returns:
        分组信息列表
    """
    registry = get_tool_registry()
    groups = registry.list_groups()
    return [
        {
            "code": g.code,
            "name": g.name,
            "category": g.category.value,
            "operation_type": g.operation_type.value,
            "description": g.description,
            "tool_count": len(g.tools),
        }
        for g in groups
    ]


def list_permissions() -> List[dict]:
    """
    列出所有工具权限

    Returns:
        权限信息列表
    """
    registry = get_tool_registry()
    permissions = registry.get_permissions()
    return [
        {
            "code": p.code,
            "name": p.name,
            "description": p.description,
            "groups": p.groups,
        }
        for p in permissions
    ]


def get_tools_by_package(
    package: str,
    permissions: Optional[Set[str]] = None,
    user_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> List[Any]:
    """
    获取指定包的工具

    Args:
        package: 包名（如 "k8s", "prometheus", "loki"）
        permissions: 用户权限集合（可选）
        user_id: 用户 ID（可选，用于动态获取权限）
        db: 数据库会话（可选，用于动态获取权限）

    Returns:
        LangChain 工具列表
    """
    registry = get_tool_registry()

    # 如果提供了 user_id 和 db，动态获取权限
    if permissions is None and user_id is not None and db is not None:
        return registry.get_langchain_tools(package=package, user_id=user_id, db=db)

    # 传 db 做集成开关检查
    return registry.get_langchain_tools(package=package, permissions=permissions, db=db)  # type: ignore[arg-type]


def get_available_packages() -> List[str]:
    """
    获取可用的工具包列表

    Returns:
        包名列表（如 ["k8s", "prometheus", "loki"]）
    """
    registry = get_tool_registry()
    packages = set()

    for group in registry.list_groups():
        # 从 group_code 中提取包名（如 "k8s.read" -> "k8s"）
        package = group.code.split('.')[0]
        packages.add(package)

    return sorted(packages)


def scan_all_tools() -> List[dict]:
    """
    扫描并返回所有工具的详细信息

    用于前端页面动态获取工具列表并同步到数据库。
    此方法会触发工具注册表的初始化（如果尚未初始化）。

    Returns:
        工具信息列表，包含：
        - name: 工具名称
        - group: 工具分组
        - operation_type: 操作类型
        - risk_level: 风险等级
        - permissions: 所需权限
        - description: 描述
        - enabled: 是否启用
    """
    registry = get_tool_registry()
    tools_info = []

    for tool_class in registry.list_tools():
        metadata = tool_class.get_metadata()
        if not metadata:
            continue

        tools_info.append({
            "name": metadata.name,
            "group": metadata.group or "default",
            "operation_type": metadata.operation_type.value if metadata.operation_type else "unknown",
            "risk_level": metadata.risk_level.value if metadata.risk_level else "unknown",
            "permissions": metadata.permissions or [],
            "description": metadata.description or "",
            "enabled": metadata.enabled,
            "expose_to_agent": metadata.expose_to_agent,
        })

    return tools_info


__all__ = [
    "get_all_tools",
    "get_tools_by_group",
    "get_tools_by_package",
    "get_available_packages",
    "list_groups",
    "list_permissions",
    "scan_all_tools",
]
