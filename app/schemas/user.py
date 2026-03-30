# app/schemas/user.py
"""用户相关的 Pydantic 模型"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    """用户基础模型"""

    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱")
    full_name: Optional[str] = Field(None, max_length=100, description="全名")


class UserCreate(UserBase):
    """创建用户模型"""

    password: str = Field(..., min_length=8, description="密码（最少8个字符）")


class UserUpdate(BaseModel):
    """更新用户模型"""

    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    feishu_user_id: Optional[str] = Field(None, max_length=100, description="飞书用户ID")


class FeishuBindRequest(BaseModel):
    """绑定飞书账号请求模型"""

    feishu_user_id: str = Field(..., min_length=1, max_length=100, description="飞书用户ID")


class UserInDB(UserBase):
    """数据库中的用户模型"""

    id: int
    is_active: bool
    is_superuser: bool
    feishu_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime]

    class Config:
        from_attributes = True


class UserResponse(UserInDB):
    """用户响应模型（不包含敏感信息）"""

    pass


class LoginRequest(BaseModel):
    """登录请求模型"""

    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    remember: bool = Field(False, description="记住我（7天）")


class LoginResponse(BaseModel):
    """登录响应模型"""

    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field("bearer", description="令牌类型")
    user: UserResponse = Field(..., description="用户信息")


class TokenPayload(BaseModel):
    """Token payload 模型"""

    sub: str = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    is_superuser: bool = Field(..., description="是否超级管理员")
    exp: int = Field(..., description="过期时间")
    iat: int = Field(..., description="签发时间")


class ResetPasswordRequest(BaseModel):
    """重置密码请求模型"""

    new_password: str = Field(..., min_length=8, description="新密码（最少8个字符）")
