# app/api/v1/users.py
"""用户管理 API 端点"""

import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.core.security import hash_password
from app.core.deps import get_current_user, get_current_admin
from app.core.permission_checker import check_user_permission
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.schemas.user import FeishuBindRequest, ResetPasswordRequest
from app.schemas.rbac import UserRoleAssign, UserRoleResponse, RoleResponse

router = APIRouter(prefix="/users", tags=["users"])
logger = logging.getLogger(__name__)


def _check_manage_permission(current_user: User, db: Session):  # type: ignore[no-untyped-def]
    """检查用户是否有 manage_users 或 manage_roles 权限"""
    has_manage_users = check_user_permission(db, current_user.id, "manage_users")  # type: ignore[arg-type]
    has_manage_roles = check_user_permission(db, current_user.id, "manage_roles")  # type: ignore[arg-type]

    if not (has_manage_users or has_manage_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="没有权限: manage_users 或 manage_roles"
        )


@router.get("", response_model=List[UserResponse])
async def list_users(  # type: ignore[no-untyped-def]
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """获取用户列表（仅管理员）"""
    users = db.query(User).offset(skip).limit(limit).all()
    return [UserResponse.model_validate(user) for user in users]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(  # type: ignore[no-untyped-def]
    user_id: int, current_user: User = Depends(get_current_admin), db: Session = Depends(get_db)
):
    """获取用户详情（仅管理员）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return UserResponse.model_validate(user)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(  # type: ignore[no-untyped-def]
    user_data: UserCreate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """创建新用户（仅管理员）"""
    # 检查用户名是否已存在
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 检查邮箱是否已存在
    existing_email = db.query(User).filter(User.email == user_data.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="邮箱已被使用")

    # 创建新用户
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
        is_active=True,
        is_superuser=False,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    logger.info(f"Admin {current_user.username} created user {new_user.username}")

    return UserResponse.model_validate(new_user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(  # type: ignore[no-untyped-def]
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """更新用户信息（仅管理员）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 更新字段
    if user_data.email is not None:
        # 检查邮箱是否被其他用户使用
        existing = db.query(User).filter(User.email == user_data.email, User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="邮箱已被使用")
        user.email = user_data.email  # type: ignore[assignment]

    if user_data.full_name is not None:
        user.full_name = user_data.full_name  # type: ignore[assignment]

    if user_data.is_active is not None:
        user.is_active = user_data.is_active  # type: ignore[assignment]

    if user_data.feishu_user_id is not None:
        # 检查飞书ID是否被其他用户使用
        if user_data.feishu_user_id:  # 非空字符串才检查
            existing = (
                db.query(User)
                .filter(User.feishu_user_id == user_data.feishu_user_id, User.id != user_id)
                .first()
            )
            if existing:
                raise HTTPException(status_code=400, detail="该飞书ID已被其他用户绑定")
        user.feishu_user_id = user_data.feishu_user_id  # type: ignore[assignment]

    db.commit()
    db.refresh(user)

    logger.info(f"Admin {current_user.username} updated user {user.username}")

    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(  # type: ignore[no-untyped-def]
    user_id: int, current_user: User = Depends(get_current_admin), db: Session = Depends(get_db)
):
    """删除用户（仅管理员）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 不允许删除自己
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")

    db.delete(user)
    db.commit()

    logger.info(f"Admin {current_user.username} deleted user {user.username}")

    return None


@router.post("/{user_id}/reset-password")
async def reset_user_password(  # type: ignore[no-untyped-def]
    user_id: int,
    request: ResetPasswordRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """重置用户密码（仅管理员）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.hashed_password = hash_password(request.new_password)  # type: ignore[assignment]
    db.commit()

    logger.info(f"Admin {current_user.username} reset password for user {user.username}")

    return {"message": "密码重置成功"}


@router.get("/{user_id}/roles", response_model=List[RoleResponse])
async def get_user_roles(  # type: ignore[no-untyped-def]
    user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """获取用户的角色列表"""
    _check_manage_permission(current_user, db)

    # 检查用户是否存在
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"用户不存在: {user_id}")

    # 查询用户的角色
    roles = (
        db.query(Role)
        .join(UserRole, Role.id == UserRole.role_id)
        .filter(UserRole.user_id == user_id)
        .order_by(Role.id)
        .all()
    )

    logger.info(f"User {current_user.username} viewed {len(roles)} roles for user: {user.username}")

    return roles


@router.put("/{user_id}/roles", response_model=UserRoleResponse)
async def assign_roles_to_user(  # type: ignore[no-untyped-def]
    user_id: int,
    role_data: UserRoleAssign,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """批量分配角色到用户（替换现有角色）"""
    _check_manage_permission(current_user, db)

    # 检查用户是否存在
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"用户不存在: {user_id}")

    # 验证所有角色代码是否存在
    role_codes = role_data.role_codes
    roles = db.query(Role).filter(Role.code.in_(role_codes)).all()

    found_codes = {r.code for r in roles}
    missing_codes = set(role_codes) - found_codes

    if missing_codes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"角色代码不存在: {', '.join(missing_codes)}",
        )

    # 删除现有的用户角色关联
    db.query(UserRole).filter(UserRole.user_id == user_id).delete()

    # 创建新的用户角色关联
    for role in roles:
        user_role = UserRole(user_id=user_id, role_id=role.id)
        db.add(user_role)

    db.commit()

    # 获取更新后的角色列表
    updated_roles = (
        db.query(Role)
        .join(UserRole, Role.id == UserRole.role_id)
        .filter(UserRole.user_id == user_id)
        .order_by(Role.id)
        .all()
    )

    logger.info(
        f"User {current_user.username} assigned {len(roles)} roles to user: {user.username}"
    )

    return UserRoleResponse(user_id=user_id, roles=updated_roles)  # type: ignore[arg-type]


@router.post("/me/bind-feishu", response_model=UserResponse)
async def bind_feishu_account(  # type: ignore[no-untyped-def]
    bind_data: FeishuBindRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """绑定飞书账号（用户自己绑定）"""
    # 检查飞书ID是否已被其他用户绑定
    existing_user = (
        db.query(User)
        .filter(User.feishu_user_id == bind_data.feishu_user_id, User.id != current_user.id)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="该飞书账号已被其他用户绑定"
        )

    # 绑定飞书ID
    current_user.feishu_user_id = bind_data.feishu_user_id  # type: ignore[assignment]
    db.commit()
    db.refresh(current_user)

    logger.info(f"User {current_user.username} bound Feishu account: {bind_data.feishu_user_id}")

    return UserResponse.model_validate(current_user)


@router.delete("/me/unbind-feishu", response_model=UserResponse)
async def unbind_feishu_account(  # type: ignore[no-untyped-def]
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """解绑飞书账号（用户自己解绑）"""
    if not current_user.feishu_user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="您还未绑定飞书账号")

    # 解绑飞书ID
    current_user.feishu_user_id = None  # type: ignore[assignment]
    db.commit()
    db.refresh(current_user)

    logger.info(f"User {current_user.username} unbound Feishu account")

    return UserResponse.model_validate(current_user)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):  # type: ignore[no-untyped-def]
    """获取当前登录用户信息"""
    return UserResponse.model_validate(current_user)
