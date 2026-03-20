# app/core/permissions.py
"""权限点定义"""

from enum import Enum
from typing import List
from dataclasses import dataclass


class PermissionCategory(str, Enum):
    """权限分类"""

    MENU = "menu"
    TOOL = "tool"
    API = "api"


@dataclass
class PermissionDef:
    """权限定义"""

    code: str
    name: str
    category: PermissionCategory
    resource: str
    description: str = ""


# ============ 菜单权限 ============
MENU_PERMISSIONS = [
    PermissionDef(
        code="view_dashboard",
        name="查看仪表盘",
        category=PermissionCategory.MENU,
        resource="dashboard",
        description="允许访问仪表盘页面",
    ),
    PermissionDef(
        code="execute_workflow",
        name="执行工作流",
        category=PermissionCategory.MENU,
        resource="workflow_execute",
        description="允许访问工作流执行页面",
    ),
    PermissionDef(
        code="view_history",
        name="查看执行历史",
        category=PermissionCategory.MENU,
        resource="history",
        description="允许访问执行历史页面",
    ),
    PermissionDef(
        code="view_diagnostics",
        name="查看API诊断",
        category=PermissionCategory.MENU,
        resource="diagnostics",
        description="允许访问API诊断页面",
    ),
    PermissionDef(
        code="manage_users",
        name="管理用户",
        category=PermissionCategory.MENU,
        resource="users",
        description="允许访问用户管理页面",
    ),
    PermissionDef(
        code="manage_roles",
        name="管理角色权限",
        category=PermissionCategory.MENU,
        resource="roles",
        description="允许访问角色权限管理页面",
    ),
    PermissionDef(
        code="view_settings",
        name="查看系统设置",
        category=PermissionCategory.MENU,
        resource="settings",
        description="允许访问系统设置页面",
    ),
]


# ============ Tool 权限 ============
TOOL_PERMISSIONS = [
    # ===== K8s 工具权限 =====
    PermissionDef(
        code="k8s.view",
        name="K8s 查看权限",
        category=PermissionCategory.TOOL,
        resource="k8s",
        description="允许查看 Kubernetes 资源（Pod、Deployment、Service、Node 等）",
    ),
    PermissionDef(
        code="k8s.delete",
        name="K8s 删除权限",
        category=PermissionCategory.TOOL,
        resource="k8s",
        description="允许删除 Kubernetes 资源（Pod、Deployment、Service 等）",
    ),
    PermissionDef(
        code="k8s.restart",
        name="K8s 重启权限",
        category=PermissionCategory.TOOL,
        resource="k8s",
        description="允许重启 Kubernetes Deployment",
    ),
    PermissionDef(
        code="k8s.scale",
        name="K8s 扩缩容权限",
        category=PermissionCategory.TOOL,
        resource="k8s",
        description="允许扩缩容 Kubernetes Deployment",
    ),
    PermissionDef(
        code="k8s.update",
        name="K8s 更新权限",
        category=PermissionCategory.TOOL,
        resource="k8s",
        description="允许更新 Kubernetes 资源（ConfigMap、Secret 等）",
    ),
    PermissionDef(
        code="k8s.execute",
        name="K8s 命令执行权限",
        category=PermissionCategory.TOOL,
        resource="k8s",
        description="允许执行 kubectl 命令",
    ),
    # ===== Prometheus 工具权限 =====
    PermissionDef(
        code="prometheus.query",
        name="Prometheus 查询权限",
        category=PermissionCategory.TOOL,
        resource="prometheus",
        description="允许查询 Prometheus 指标数据",
    ),
    # ===== Loki 工具权限 =====
    PermissionDef(
        code="loki.query",
        name="Loki 日志查询权限",
        category=PermissionCategory.TOOL,
        resource="loki",
        description="允许查询 Loki 日志数据",
    ),
    # ===== 命令执行工具权限 =====
    PermissionDef(
        code="command.execute",
        name="命令执行权限",
        category=PermissionCategory.TOOL,
        resource="command",
        description="允许执行系统命令",
    ),
]


# ============ API 权限 ============
API_PERMISSIONS = [
    PermissionDef(
        code="api:workflow:execute",
        name="执行工作流API",
        category=PermissionCategory.API,
        resource="api:workflow:execute",
        description="允许调用工作流执行API",
    ),
    PermissionDef(
        code="api:workflow:resume",
        name="恢复工作流API",
        category=PermissionCategory.API,
        resource="api:workflow:resume",
        description="允许调用工作流恢复API",
    ),
    PermissionDef(
        code="api:users:read",
        name="读取用户API",
        category=PermissionCategory.API,
        resource="api:users:read",
        description="允许调用用户读取API",
    ),
    PermissionDef(
        code="api:users:write",
        name="写入用户API",
        category=PermissionCategory.API,
        resource="api:users:write",
        description="允许调用用户写入API",
    ),
]


# ============ 辅助函数 ============
def get_all_permissions() -> List[PermissionDef]:
    """获取所有权限"""
    return MENU_PERMISSIONS + TOOL_PERMISSIONS + API_PERMISSIONS


def get_permissions_by_category(category: PermissionCategory) -> List[PermissionDef]:
    """按分类获取权限"""
    all_perms = get_all_permissions()
    return [p for p in all_perms if p.category == category]


def get_permission_by_code(code: str) -> PermissionDef | None:
    """根据代码获取权限定义"""
    all_perms = get_all_permissions()
    for perm in all_perms:
        if perm.code == code:
            return perm
    return None
