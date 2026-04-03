# app/core/permission_checker.py
"""权限检查模块 - 支持请求级缓存"""

import logging
from typing import List, Callable, Any, Optional
from functools import wraps

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.models.user_role import UserRole
from app.models.user import User
from app.core.deps import get_current_user
from app.models.database import get_db, SessionLocal
from app.utils.logger import get_request_context, set_request_context

logger = logging.getLogger(__name__)

# 缓存键前缀，避免与其他上下文数据冲突
PERMISSION_CACHE_KEY = "_cached_user_permissions"


def _get_cached_permissions(user_id: int) -> Optional[List[str]]:
    """
    从请求上下文获取缓存的权限列表

    Args:
        user_id: 用户ID

    Returns:
        缓存的权限代码列表，如果未缓存则返回 None
    """
    ctx = get_request_context()
    cached = ctx.get(PERMISSION_CACHE_KEY, {})
    if cached.get("user_id") == user_id:
        return cached.get("permissions")  # type: ignore[no-any-return]
    return None


def _cache_permissions(user_id: int, permissions: List[str]) -> None:
    """
    将权限列表缓存到请求上下文

    Args:
        user_id: 用户ID
        permissions: 权限代码列表
    """
    ctx = get_request_context()
    ctx[PERMISSION_CACHE_KEY] = {
        "user_id": user_id,
        "permissions": permissions,
    }
    # 更新上下文
    set_request_context(
        session_id=ctx.get('session_id', 'no-sess'),
        request_id=ctx.get('request_id'),  # type: ignore[arg-type]
        user_id=ctx.get('user_id'),  # type: ignore[arg-type]
        channel=ctx.get('channel'),  # type: ignore[arg-type]
        user_permissions=permissions,
    )


def check_user_permission(db: Session, user_id: int, permission_code: str) -> bool:
    """
    检查用户是否有指定权限（支持请求级缓存）

    首次调用时会加载该用户的所有权限并缓存到请求上下文，
    后续调用直接从缓存读取，避免 N+1 查询问题。

    Args:
        db: 数据库会话
        user_id: 用户ID
        permission_code: 权限代码

    Returns:
        bool: 是否有权限
    """
    # 1. 尝试从缓存获取权限列表
    cached_permissions = _get_cached_permissions(user_id)

    if cached_permissions is not None:
        # 使用缓存的权限列表进行判断
        return permission_code in cached_permissions

    # 2. 缓存未命中，查询该用户的所有权限并缓存
    permissions = (
        db.query(Permission)
        .join(RolePermission, Permission.id == RolePermission.permission_id)
        .join(UserRole, RolePermission.role_id == UserRole.role_id)
        .filter(UserRole.user_id == user_id)
        .distinct()
        .all()
    )

    # 提取权限代码并缓存
    permission_codes = [p.code for p in permissions]
    _cache_permissions(user_id, permission_codes)  # type: ignore[arg-type]

    # 3. 返回检查结果
    return permission_code in permission_codes


def get_user_permissions(db: Session, user_id: int) -> List[Permission]:
    """
    获取用户的所有权限（支持请求级缓存）

    注意：此函数直接返回 Permission 对象列表。
    如果只需要权限代码，建议使用 get_user_permission_codes() 以获得更好的缓存效果。

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

    # 同时缓存权限代码，供后续 check_user_permission 使用
    permission_codes = [p.code for p in permissions]
    _cache_permissions(user_id, permission_codes)  # type: ignore[arg-type]

    return permissions


def get_user_permission_codes(db: Session, user_id: int) -> List[str]:
    """
    获取用户的所有权限代码（支持请求级缓存）

    优先从缓存读取，避免重复数据库查询。

    Args:
        db: 数据库会话
        user_id: 用户ID

    Returns:
        List[str]: 权限代码列表
    """
    # 1. 尝试从缓存获取
    cached = _get_cached_permissions(user_id)
    if cached is not None:
        return cached

    # 2. 缓存未命中，查询数据库
    permissions = (
        db.query(Permission.code)
        .join(RolePermission, Permission.id == RolePermission.permission_id)
        .join(UserRole, RolePermission.role_id == UserRole.role_id)
        .filter(UserRole.user_id == user_id)
        .distinct()
        .all()
    )

    # 3. 缓存并返回
    permission_codes = [p.code for p in permissions]
    _cache_permissions(user_id, permission_codes)

    return permission_codes


def is_admin(db: Session, user_id: int) -> bool:
    """
    检查用户是否是管理员

    Args:
        db: 数据库会话
        user_id: 用户ID

    Returns:
        bool: 是否是管理员
    """
    user = db.query(User).filter(User.id == user_id).first()
    return user is not None and user.is_superuser  # type: ignore[return-value]


def require_permission(permission_code: str):  # type: ignore[no-untyped-def]
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

    def decorator(func):  # type: ignore[no-untyped-def]
        @wraps(func)
        async def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
            current_user = kwargs.get("current_user")
            db = kwargs.get("db")

            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录"
                )

            has_permission = check_user_permission(db, current_user.id, permission_code)

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"没有权限: {permission_code}",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_any_permission(*permission_codes: str):  # type: ignore[no-untyped-def]
    """
    检查用户是否有任意一个权限

    用法：
        @require_any_permission("manage_users", "manage_roles")
        async def some_endpoint(...):
            pass
    """

    def decorator(func):  # type: ignore[no-untyped-def]
        @wraps(func)
        async def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
            current_user = kwargs.get("current_user")
            db = kwargs.get("db")

            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录"
                )

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


class ToolPermissionDenied(Exception):
    """工具权限拒绝异常"""

    def __init__(self, permission_code: str, message: str = None):  # type: ignore[assignment]
        self.permission_code = permission_code
        self.message = message or f"没有权限执行此操作: {permission_code}"
        super().__init__(self.message)


def require_tool_permission(permission_code: str):  # type: ignore[no-untyped-def]
    """
    工具权限检查装饰器

    用于 @tool 装饰的工具函数，在执行前检查用户权限。

    用法：
        @tool
        @require_tool_permission("prometheus.query")
        async def query_cpu_usage_tool(...) -> Dict[str, Any]:
            ...

    Args:
        permission_code: 需要的权限代码

    Raises:
        ToolPermissionDenied: 用户没有该权限

    注意：
        - 此装饰器必须在 @tool 之后应用
        - 工具函数需要接受 user_id 参数或从 kwargs 中获取
        - 如果无法获取用户信息，默认拒绝操作
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:  # type: ignore[no-untyped-def]
            user_id = kwargs.get("user_id")
            db = kwargs.get("db")

            if not db:
                try:
                    db = SessionLocal()
                    should_close_db = True
                except Exception:
                    logger.warning("无法获取数据库会话，跳过权限检查")
                    should_close_db = False
            else:
                should_close_db = False

            try:
                if not user_id:
                    logger.warning(f"工具 {func.__name__} 缺少 user_id 参数，拒绝操作")
                    raise ToolPermissionDenied(
                        permission_code, message="用户信息缺失，无法验证权限"
                    )

                if db:
                    has_permission = check_user_permission(db, user_id, permission_code)
                else:
                    logger.warning(f"工具 {func.__name__} 无数据库连接，拒绝操作")
                    has_permission = False

                if not has_permission:
                    logger.info(
                        f"用户 {user_id} 尝试使用工具 {func.__name__}，"
                        f"但缺少权限: {permission_code}"
                    )
                    raise ToolPermissionDenied(permission_code)

                return await func(*args, **kwargs)

            finally:
                if should_close_db and db:
                    db.close()

        return wrapper

    return decorator


def check_tool_permission(
    db: Session, user_id: int, permission_code: str, raise_exception: bool = False
) -> bool:
    """
    检查工具权限（便捷函数）

    用法：
        if not check_tool_permission(db, user_id, "prometheus.query"):
            return {"success": False, "error": "没有权限"}

    Args:
        db: 数据库会话
        user_id: 用户ID
        permission_code: 权限代码
        raise_exception: 是否在无权限时抛出异常

    Returns:
        bool: 是否有权限

    Raises:
        ToolPermissionDenied: 当 raise_exception=True 且无权限时
    """
    has_permission = check_user_permission(db, user_id, permission_code)

    if not has_permission and raise_exception:
        raise ToolPermissionDenied(permission_code)

    return has_permission


__all__ = [
    "check_user_permission",
    "get_user_permissions",
    "get_user_permission_codes",
    "is_admin",
    "require_permission",
    "require_any_permission",
    "require_tool_permission",
    "check_tool_permission",
    "ToolPermissionDenied",
]
