# app/core/permission_checker.py
"""权限检查模块"""

from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.models.user_role import UserRole


def check_user_permission(db: Session, user_id: int, permission_code: str) -> bool:
    """
    检查用户是否有指定权限

    Args:
        db: 数据库会话
        user_id: 用户ID
        permission_code: 权限代码

    Returns:
        bool: 是否有权限
    """
    # 查询用户是否有该权限
    # 通过 user -> user_roles -> role_permissions -> permissions 关联查询
    permission = (
        db.query(Permission)
        .join(RolePermission, Permission.id == RolePermission.permission_id)
        .join(UserRole, RolePermission.role_id == UserRole.role_id)
        .filter(UserRole.user_id == user_id, Permission.code == permission_code)
        .first()
    )

    return permission is not None


def get_user_permissions(db: Session, user_id: int) -> List[Permission]:
    """
    获取用户的所有权限

    Args:
        db: 数据库会话
        user_id: 用户ID

    Returns:
        List[Permission]: 权限列表
    """
    permissions = (
        db.query(Permission)
        .join(RolePermission, Permission.id == RolePermission.permission_id)
        .join(UserRole, RolePermission.role_id == UserRole.role_id)
        .filter(UserRole.user_id == user_id)
        .distinct()
        .all()
    )

    return permissions


def get_user_permission_codes(db: Session, user_id: int) -> List[str]:
    """
    获取用户的所有权限代码

    Args:
        db: 数据库会话
        user_id: 用户ID

    Returns:
        List[str]: 权限代码列表
    """
    permissions = get_user_permissions(db, user_id)
    return [p.code for p in permissions]


from functools import wraps
from fastapi import HTTPException, status, Depends
from app.core.deps import get_current_user
from app.models.database import get_db


def require_permission(permission_code: str):
    """
    权限检查装饰器

    用法：
        @require_permission("view_dashboard")
        async def some_endpoint(...):
            pass

    Args:
        permission_code: 权限代码

    Raises:
        HTTPException: 401 未登录或 403 无权限
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从依赖注入中获取 current_user 和 db
            current_user = kwargs.get("current_user")
            db = kwargs.get("db")

            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")

            # 检查用户是否有该权限
            has_permission = check_user_permission(db, current_user.id, permission_code)

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail=f"没有权限: {permission_code}"
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_any_permission(*permission_codes: str):
    """
    检查用户是否有任意一个权限

    用法：
        @require_any_permission("manage_users", "manage_roles")
        async def some_endpoint(...):
            pass
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get("current_user")
            db = kwargs.get("db")

            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")

            # 检查是否有任意一个权限
            has_any = any(
                check_user_permission(db, current_user.id, code) for code in permission_codes
            )

            if not has_any:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"没有权限: {', '.join(permission_codes)}",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator
