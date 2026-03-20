# app/api/v1/roles.py
"""角色管理 API"""

import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.models.role import Role
from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.models.user_role import UserRole
from app.core.deps import get_current_user
from app.core.permission_checker import check_user_permission
from app.schemas.rbac import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    RoleWithPermissions,
    RolePermissionAssign,
    PermissionResponse,
)

router = APIRouter(prefix="/roles", tags=["roles"])
logger = logging.getLogger(__name__)


def _check_manage_roles_permission(current_user: User, db: Session):
    """检查用户是否有 manage_roles 权限"""
    if not check_user_permission(db, current_user.id, "manage_roles"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限: manage_roles")


def _get_role_permissions(db: Session, role_id: int) -> List[str]:
    """获取角色的权限代码列表"""
    permissions = (
        db.query(Permission)
        .join(RolePermission, Permission.id == RolePermission.permission_id)
        .filter(RolePermission.role_id == role_id)
        .all()
    )
    return [p.code for p in permissions]


@router.get("", response_model=List[RoleResponse])
async def list_roles(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取所有角色"""
    _check_manage_roles_permission(current_user, db)

    roles = db.query(Role).order_by(Role.id).all()
    logger.info(f"User {current_user.username} listed {len(roles)} roles")

    return roles


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    role_data: RoleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建新角色"""
    _check_manage_roles_permission(current_user, db)

    # 检查角色代码是否已存在
    existing_role = db.query(Role).filter(Role.code == role_data.code).first()
    if existing_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"角色代码已存在: {role_data.code}"
        )

    # 检查角色名称是否已存在
    existing_role = db.query(Role).filter(Role.name == role_data.name).first()
    if existing_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"角色名称已存在: {role_data.name}"
        )

    # 创建角色
    new_role = Role(
        name=role_data.name,
        code=role_data.code,
        description=role_data.description,
        is_system=False,  # 用户创建的角色不是系统角色
    )

    db.add(new_role)
    db.commit()
    db.refresh(new_role)

    logger.info(f"User {current_user.username} created role: {new_role.code}")

    return new_role


@router.get("/{role_id}", response_model=RoleWithPermissions)
async def get_role(
    role_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """获取角色详情（包含权限）"""
    _check_manage_roles_permission(current_user, db)

    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"角色不存在: {role_id}")

    # 获取角色的权限代码列表
    permission_codes = _get_role_permissions(db, role_id)

    # 构建响应
    role_dict = {
        "id": role.id,
        "name": role.name,
        "code": role.code,
        "description": role.description,
        "is_system": role.is_system,
        "created_at": role.created_at,
        "updated_at": role.updated_at,
        "permissions": permission_codes,
    }

    logger.info(f"User {current_user.username} viewed role: {role.code}")

    return RoleWithPermissions(**role_dict)


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    role_data: RoleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新角色"""
    _check_manage_roles_permission(current_user, db)

    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"角色不存在: {role_id}")

    # 不允许更新系统角色
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能修改系统角色")

    # 检查角色名称是否已被其他角色使用
    if role_data.name is not None:
        existing_role = (
            db.query(Role).filter(Role.name == role_data.name, Role.id != role_id).first()
        )
        if existing_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"角色名称已存在: {role_data.name}"
            )
        role.name = role_data.name

    # 更新描述
    if role_data.description is not None:
        role.description = role_data.description

    db.commit()
    db.refresh(role)

    logger.info(f"User {current_user.username} updated role: {role.code}")

    return role


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """删除角色"""
    _check_manage_roles_permission(current_user, db)

    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"角色不存在: {role_id}")

    # 不允许删除系统角色
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能删除系统角色")

    # 检查角色是否已分配给用户
    user_count = db.query(UserRole).filter(UserRole.role_id == role_id).count()
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"角色已分配给 {user_count} 个用户，不能删除",
        )

    # 删除角色的权限关联
    db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()

    # 删除角色
    db.delete(role)
    db.commit()

    logger.info(f"User {current_user.username} deleted role: {role.code}")


@router.get("/{role_id}/permissions", response_model=List[PermissionResponse])
async def get_role_permissions(
    role_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """获取角色的权限列表"""
    _check_manage_roles_permission(current_user, db)

    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"角色不存在: {role_id}")

    # 查询角色的权限
    permissions = (
        db.query(Permission)
        .join(RolePermission, Permission.id == RolePermission.permission_id)
        .filter(RolePermission.role_id == role_id)
        .order_by(Permission.category, Permission.code)
        .all()
    )

    logger.info(
        f"User {current_user.username} viewed {len(permissions)} permissions for role: {role.code}"
    )

    return permissions


@router.put("/{role_id}/permissions", response_model=RoleWithPermissions)
async def assign_permissions_to_role(
    role_id: int,
    permission_data: RolePermissionAssign,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """批量分配权限到角色（替换现有权限）"""
    _check_manage_roles_permission(current_user, db)

    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"角色不存在: {role_id}")

    # 验证所有权限代码是否存在
    permission_codes = permission_data.permission_codes
    permissions = db.query(Permission).filter(Permission.code.in_(permission_codes)).all()

    found_codes = {p.code for p in permissions}
    missing_codes = set(permission_codes) - found_codes

    if missing_codes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"权限代码不存在: {', '.join(missing_codes)}",
        )

    # 删除现有的角色权限关联
    db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()

    # 创建新的角色权限关联
    for permission in permissions:
        role_permission = RolePermission(role_id=role_id, permission_id=permission.id)
        db.add(role_permission)

    db.commit()

    # 获取更新后的权限代码列表
    updated_permission_codes = _get_role_permissions(db, role_id)

    # 构建响应
    role_dict = {
        "id": role.id,
        "name": role.name,
        "code": role.code,
        "description": role.description,
        "is_system": role.is_system,
        "created_at": role.created_at,
        "updated_at": role.updated_at,
        "permissions": updated_permission_codes,
    }

    logger.info(
        f"User {current_user.username} assigned {len(permissions)} permissions to role: {role.code}"
    )

    return RoleWithPermissions(**role_dict)
