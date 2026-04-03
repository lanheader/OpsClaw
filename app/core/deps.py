# app/core/deps.py
"""依赖注入：获取当前用户"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.user import User
from app.core.security import verify_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    """
    从 Token 中获取当前用户

    Args:
        token: JWT Token
        db: 数据库会话

    Returns:
        当前用户对象

    Raises:
        HTTPException: Token 无效或用户不存在
    """
    # 验证 Token
    payload = verify_token(token)
    user_id: str = payload.get("sub")  # type: ignore[assignment]

    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的认证凭证")

    # 从数据库获取用户
    user = db.query(User).filter(User.id == int(user_id)).first()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    return user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    获取当前管理员用户（需要超级管理员权限）

    Args:
        current_user: 当前用户

    Returns:
        当前管理员用户对象

    Raises:
        HTTPException: 用户不是管理员
    """
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")

    return current_user
