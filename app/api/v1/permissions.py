# app/api/v1/permissions.py
"""权限查询 API"""

import logging
from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.models.permission import Permission
from app.core.deps import get_current_user
from app.core.permission_checker import get_user_permission_codes, is_admin
from app.core.permissions import get_all_permissions, PermissionCategory, sync_tool_permissions_to_db
from app.tools import list_permissions, list_groups
from pydantic import BaseModel

router = APIRouter(prefix="/permissions", tags=["permissions"])
logger = logging.getLogger(__name__)


class PermissionResponse(BaseModel):
    """权限响应"""

    code: str
    name: str
    category: str
    resource: str
    description: str


class UserPermissionsResponse(BaseModel):
    """用户权限响应"""

    permissions: List[str]
    roles: List[str]


@router.get("/me", response_model=UserPermissionsResponse)
async def get_my_permissions(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """获取当前用户的所有权限"""
    # 获取用户权限代码列表
    permission_codes = get_user_permission_codes(db, current_user.id)

    # 获取用户角色代码列表
    user_roles = (
        db.query(Role)
        .join(UserRole, Role.id == UserRole.role_id)
        .filter(UserRole.user_id == current_user.id)
        .all()
    )
    role_codes = [r.code for r in user_roles]

    return UserPermissionsResponse(permissions=permission_codes, roles=role_codes)


@router.get("", response_model=Dict[str, List[PermissionResponse]])
async def list_all_permissions(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """获取所有权限（按分类）- 从数据库读取"""
    # 从数据库读取所有权限
    db_permissions = db.query(Permission).all()

    # 按分类组织权限
    result = {"menu": [], "tool": [], "api": []}

    for perm in db_permissions:
        perm_response = PermissionResponse(
            code=perm.code,
            name=perm.name,
            category=perm.category,
            resource=perm.resource,
            description=perm.description or "",
        )

        if perm.category == "menu":
            result["menu"].append(perm_response)
        elif perm.category == "tool":
            result["tool"].append(perm_response)
        elif perm.category == "api":
            result["api"].append(perm_response)

    logger.info(
        f"返回权限列表: menu={len(result['menu'])}, tool={len(result['tool'])}, api={len(result['api'])}"
    )

    return result


@router.post("/sync-tool-permissions")
async def sync_tool_permissions(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """
    同步工具权限到数据库

    从 ToolRegistry 获取最新的工具权限，并同步到数据库。
    - 添加新权限
    - 删除不再使用的权限（未被角色使用的）
    """
    # 只有管理员可以执行同步操作
    if not is_admin(db, current_user.id):
        raise HTTPException(status_code=403, detail="只有管理员可以执行此操作")

    result = sync_tool_permissions_to_db(db)

    logger.info(
        f"工具权限同步完成: 添加 {result['added']} 个, 删除 {result['removed']} 个, 总计 {result['total']} 个"
    )

    return {
        "message": "工具权限同步完成",
        "result": result,
    }


@router.get("/tools", response_model=List[PermissionResponse])
async def get_tool_permissions_registry(
    current_user: User = Depends(get_current_user),
):
    """
    从 ToolRegistry 动态获取工具权限

    直接从 ToolRegistry 获取最新的工具权限，不经过数据库。
    用于前端展示当前系统支持的所有工具权限。
    """
    # 从 ToolRegistry 获取工具权限
    tool_permissions = list_permissions()

    return [
        PermissionResponse(
            code=perm["code"],
            name=perm["name"],
            category="tool",
            resource=perm.get("resource", "tool"),
            description=perm.get("description", ""),
        )
        for perm in tool_permissions
    ]


@router.get("/tools/groups")
async def get_tool_groups(
    current_user: User = Depends(get_current_user),
):
    """
    获取工具分组信息

    返回所有工具分组及其包含的工具数量。
    """
    groups = list_groups()

    return {
        "groups": groups,
        "total": len(groups),
    }
