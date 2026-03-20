"""系统设置相关的 Pydantic 模型"""

from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


class SystemSettingBase(BaseModel):
    """系统设置基础模型"""

    key: str = Field(..., description="设置键")
    value: Optional[str] = Field(None, description="设置值")
    category: str = Field(..., description="设置分类")
    name: str = Field(..., description="设置名称")
    description: Optional[str] = Field(None, description="设置描述")
    value_type: str = Field("string", description="值类型: string, number, boolean, json")
    is_sensitive: bool = Field(False, description="是否敏感信息")
    is_readonly: bool = Field(False, description="是否只读")


class SystemSettingCreate(SystemSettingBase):
    """创建系统设置模型"""

    pass


class SystemSettingUpdate(BaseModel):
    """更新系统设置模型"""

    value: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None


class SystemSettingResponse(SystemSettingBase):
    """系统设置响应模型"""

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SystemSettingBatchUpdate(BaseModel):
    """批量更新系统设置模型"""

    settings: dict[str, Any] = Field(..., description="设置键值对")
