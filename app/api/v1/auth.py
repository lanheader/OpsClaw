# app/api/v1/auth.py
"""用户认证 API 端点"""

import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.models.login_history import LoginHistory
from app.core.security import verify_password, create_access_token, get_access_token_expire_days
from app.core.deps import get_current_user
from app.schemas.user import LoginRequest, LoginResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.post("/login", response_model=LoginResponse)
async def login(request: Request, login_data: LoginRequest, db: Session = Depends(get_db)):  # type: ignore[no-untyped-def]
    """用户登录"""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    user = db.query(User).filter(User.username == login_data.username).first()

    if not user or not verify_password(login_data.password, user.hashed_password):  # type: ignore[arg-type]
        # Record failure only when user exists (avoid leaking user existence)
        if user:
            db.add(
                LoginHistory(
                    user_id=user.id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    login_status="failed",
                    failure_reason="密码错误",
                )
            )
            db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    expire_delta = timedelta(days=get_access_token_expire_days()) if login_data.remember else None
    token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "is_superuser": user.is_superuser},
        expires_delta=expire_delta,
    )

    db.add(
        LoginHistory(
            user_id=user.id, ip_address=ip_address, user_agent=user_agent, login_status="success"
        )
    )
    user.last_login_at = datetime.utcnow()  # type: ignore[assignment]
    db.commit()

    logger.info(f"User {user.username} logged in from {ip_address}")

    return LoginResponse(
        access_token=token, token_type="bearer", user=UserResponse.model_validate(user)
    )


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):  # type: ignore[no-untyped-def]
    """用户登出（客户端删除 Token）"""
    logger.info(f"User {current_user.username} logged out")
    return {"message": "登出成功"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):  # type: ignore[no-untyped-def]
    """获取当前用户信息"""
    return UserResponse.model_validate(current_user)
