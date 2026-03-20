"""工具权限映射器

定义工具与权限的映射关系，用于根据用户权限动态过滤可用工具。
"""

from typing import Dict, List, Set

# 工具权限映射表
# 格式: {tool_name: [required_permission_codes]}
TOOL_PERMISSION_MAP: Dict[str, List[str]] = {
    # ===== K8s 只读工具 =====
    "get_pods_sdk": ["k8s.view"],
    "get_deployments_sdk": ["k8s.view"],
    "get_services_sdk": ["k8s.view"],
    "get_nodes_sdk": ["k8s.view"],
    "get_pod_logs_sdk": ["k8s.view"],
    "get_pod_events_sdk": ["k8s.view"],
    # ===== K8s 写操作工具 =====
    "delete_pod": ["k8s.delete"],
    "delete_deployment": ["k8s.delete"],
    "delete_service": ["k8s.delete"],
    "restart_deployment": ["k8s.restart"],
    "scale_deployment": ["k8s.scale"],
    "update_configmap": ["k8s.update"],
    "update_secret": ["k8s.update"],
    # ===== Prometheus 工具 =====
    "query_prometheus": ["prometheus.query"],
    "query_range_prometheus": ["prometheus.query"],
    "get_metrics": ["prometheus.query"],
    # ===== Loki 工具 =====
    "query_loki_logs": ["loki.query"],
    "query_loki_range": ["loki.query"],
    # ===== 命令执行工具 =====
    "execute_command": ["command.execute"],
    "execute_kubectl_command": ["k8s.execute"],
    "execute_shell_command": ["command.execute"],
}

# 权限分类
PERMISSION_CATEGORIES = {
    "k8s.view": "K8s 查看权限",
    "k8s.delete": "K8s 删除权限",
    "k8s.restart": "K8s 重启权限",
    "k8s.scale": "K8s 扩缩容权限",
    "k8s.update": "K8s 更新权限",
    "k8s.execute": "K8s 命令执行权限",
    "prometheus.query": "Prometheus 查询权限",
    "loki.query": "Loki 日志查询权限",
    "command.execute": "命令执行权限",
}


def get_required_permissions_for_tool(tool_name: str) -> List[str]:
    """
    获取工具所需的权限列表

    Args:
        tool_name: 工具名称

    Returns:
        权限代码列表
    """
    return TOOL_PERMISSION_MAP.get(tool_name, [])


def filter_tools_by_permissions(tools: List, user_permissions: Set[str]) -> List:
    """
    根据用户权限过滤工具列表

    Args:
        tools: 工具列表（LangChain Tool 对象）
        user_permissions: 用户权限代码集合

    Returns:
        过滤后的工具列表
    """
    filtered_tools = []

    for tool in tools:
        tool_name = tool.name
        required_permissions = get_required_permissions_for_tool(tool_name)

        # 如果工具没有定义权限要求，默认允许（向后兼容）
        if not required_permissions:
            filtered_tools.append(tool)
            continue

        # 检查用户是否有所有必需的权限
        has_all_permissions = all(perm in user_permissions for perm in required_permissions)

        if has_all_permissions:
            filtered_tools.append(tool)

    return filtered_tools


def get_missing_permissions_for_tool(tool_name: str, user_permissions: Set[str]) -> List[str]:
    """
    获取用户使用某个工具所缺少的权限

    Args:
        tool_name: 工具名称
        user_permissions: 用户权限代码集合

    Returns:
        缺少的权限代码列表
    """
    required_permissions = get_required_permissions_for_tool(tool_name)
    missing = [perm for perm in required_permissions if perm not in user_permissions]
    return missing


def check_tool_permission(tool_name: str, user_permissions: Set[str]) -> bool:
    """
    检查用户是否有权限使用某个工具

    Args:
        tool_name: 工具名称
        user_permissions: 用户权限代码集合

    Returns:
        是否有权限
    """
    required_permissions = get_required_permissions_for_tool(tool_name)

    # 如果工具没有定义权限要求，默认允许
    if not required_permissions:
        return True

    # 检查用户是否有所有必需的权限
    return all(perm in user_permissions for perm in required_permissions)


def get_all_tool_permissions() -> Dict[str, str]:
    """
    获取所有工具权限的描述

    Returns:
        权限代码到描述的映射
    """
    return PERMISSION_CATEGORIES.copy()
