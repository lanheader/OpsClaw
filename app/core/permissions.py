# app/core/permissions.py
"""权限点定义"""

from enum import Enum
from typing import List, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


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


# ============ Tool 权限（动态从 ToolRegistry 获取）============
def get_tool_permissions() -> List[PermissionDef]:
    """
    动态从 ToolRegistry 获取工具权限

    Returns:
        工具权限列表
    """
    try:
        from app.tools.registry import get_tool_registry

        registry = get_tool_registry()
        tool_permissions = registry.get_permissions()

        return [
            PermissionDef(
                code=perm.code,
                name=perm.name,
                category=PermissionCategory.TOOL,
                # 从权限代码提取 resource (如 k8s.view -> k8s)
                resource=perm.code.split('.')[0] if '.' in perm.code else 'tool',
                description=perm.description,
            )
            for perm in tool_permissions
        ]
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to get tool permissions from registry: {e}")
        return []


# ============ API 权限 ============
# 注意：API 权限为硬编码，新增 API 时需要手动添加
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

def get_all_permissions() -> List[PermissionDef]:
    """
    获取所有权限

    注意：
    - 菜单权限：硬编码
    - 工具权限：动态从 ToolRegistry 获取
    - API 权限：硬编码（新增 API 时需手动添加）

    Returns:
        所有权限列表（菜单 + 工具 + API）
    """
    return MENU_PERMISSIONS + get_tool_permissions() + API_PERMISSIONS


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


def sync_tool_permissions_to_db(db: "Session") -> dict:
    """
    将工具权限同步到数据库

    Args:
        db: 数据库会话

    Returns:
        同步结果统计
    """
    from app.models.permission import Permission

    # 获取当前工具权限
    tool_perm_defs = get_tool_permissions()
    tool_codes = {p.code for p in tool_perm_defs}

    # 获取数据库中现有的 tool 类型的权限
    existing_tool_perms = db.query(Permission).filter(Permission.category == "tool").all()
    existing_codes = {p.code for p in existing_tool_perms}

    # 找出需要添加和需要删除的权限
    to_add = tool_codes - existing_codes
    to_remove = existing_codes - tool_codes

    # 添加新权限
    added_count = 0
    for code in to_add:
        perm_def = next(p for p in tool_perm_defs if p.code == code)
        # 从权限代码提取 resource (如 k8s.view -> k8s)
        resource = perm_def.code.split('.')[0] if '.' in perm_def.code else 'tool'
        db_perm = Permission(
            code=perm_def.code,
            name=perm_def.name,
            category=perm_def.category.value,
            resource=resource,
            description=perm_def.description,
        )
        db.add(db_perm)
        added_count += 1

    # 删除过期权限（软删除：只删除不在 ToolRegistry 中的）
    # 注意：如果权限已被角色使用，应该标记而不是直接删除
    removed_count = 0
    for code in to_remove:
        db_perm = db.query(Permission).filter(Permission.code == code).first()
        if db_perm:
            # 检查是否有角色在使用此权限
            from app.models.role_permission import RolePermission
            usage_count = db.query(RolePermission).filter(RolePermission.permission_id == db_perm.id).count()
            if usage_count == 0:
                db.delete(db_perm)
                removed_count += 1
            else:
                import logging
                logging.getLogger(__name__).warning(
                    f"权限 {code} 仍被 {usage_count} 个角色使用，跳过删除"
                )

    db.commit()

    return {
        "added": added_count,
        "removed": removed_count,
        "total": len(tool_perm_defs),
        "added_codes": list(to_add),
        "removed_codes": list(to_remove),
    }
