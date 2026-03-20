# app/schemas/rbac.py
"""RBAC 相关的 Pydantic 模型"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# ========== 角色 Schemas ==========


class RoleBase(BaseModel):
    """角色基础模型"""

    name: str = Field(..., min_length=1, max_length=50, description="角色名称")
    code: str = Field(..., min_length=1, max_length=50, description="角色代码")
    description: Optional[str] = Field(None, max_length=200, description="角色描述")


class RoleCreate(RoleBase):
    """创建角色模型"""

    pass


class RoleUpdate(BaseModel):
    """更新角色模型"""

    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = None


class RoleResponse(RoleBase):
    """角色响应模型"""

    id: int
    is_system: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RoleWithPermissions(RoleResponse):
    """角色及其权限"""

    permissions: List[str] = Field(default_factory=list, description="权限代码列表")


# ========== 权限 Schemas ==========


class PermissionBase(BaseModel):
    """权限基础模型"""

    name: str = Field(..., max_length=100, description="权限名称")
    code: str = Field(..., max_length=100, description="权限代码")
    category: str = Field(..., max_length=50, description="权限分类")
    resource: str = Field(..., max_length=100, description="资源标识")
    description: Optional[str] = Field(None, max_length=200, description="权限描述")


class PermissionResponse(PermissionBase):
    """权限响应模型"""

    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ========== 角色权限关联 Schemas ==========


class RolePermissionAssign(BaseModel):
    """分配权限到角色"""

    permission_codes: List[str] = Field(..., description="权限代码列表")


class RolePermissionRemove(BaseModel):
    """从角色移除权限"""

    permission_codes: List[str] = Field(..., description="权限代码列表")


# ========== 用户角色关联 Schemas ==========


class UserRoleAssign(BaseModel):
    """分配角色到用户"""

    role_codes: List[str] = Field(..., description="角色代码列表")


class UserRoleResponse(BaseModel):
    """用户角色响应"""

    user_id: int
    roles: List[RoleResponse]
