"""提示词管理相关的 Pydantic 模型"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime


class AgentPromptBase(BaseModel):
    """提示词基础模型"""

    agent_name: str = Field(..., min_length=1, max_length=50, description="Agent 标识符")
    name: str = Field(..., min_length=1, max_length=100, description="显示名称")
    description: Optional[str] = Field(None, description="描述")
    content: str = Field(..., min_length=1, description="提示词内容")


class AgentPromptCreate(AgentPromptBase):
    """创建提示词模型"""

    pass


class AgentPromptUpdate(BaseModel):
    """更新提示词模型"""

    name: Optional[str] = Field(None, max_length=100, description="显示名称")
    description: Optional[str] = Field(None, description="描述")
    content: Optional[str] = Field(None, min_length=1, description="提示词内容")
    is_active: Optional[bool] = Field(None, description="是否激活")


class AgentPromptResponse(BaseModel):
    """提示词响应模型"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_name: str
    name: str
    description: Optional[str]
    content: str
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AgentPromptListItem(BaseModel):
    """提示词列表项（不含完整内容）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_name: str
    name: str
    description: Optional[str]
    version: int
    is_active: bool
    content_preview: Optional[str] = Field(None, description="内容预览（前 200 字符）")
    created_at: datetime
    updated_at: datetime


class PromptVersionResponse(BaseModel):
    """版本历史响应模型"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    prompt_id: int
    agent_name: str
    version: int
    content: str
    change_summary: Optional[str]
    changed_by: Optional[str]
    created_at: datetime


class PromptVersionListItem(BaseModel):
    """版本历史列表项（不含完整内容）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    prompt_id: int
    agent_name: str
    version: int
    content_preview: Optional[str] = Field(None, description="内容预览（前 200 字符）")
    change_summary: Optional[str]
    changed_by: Optional[str]
    created_at: datetime


class RollbackRequest(BaseModel):
    """回滚请求模型"""

    target_version: int = Field(..., ge=1, description="目标版本号")


class RollbackResponse(BaseModel):
    """回滚响应模型"""

    success: bool
    message: str
    current_version: int


class ClearCacheResponse(BaseModel):
    """清除缓存响应模型"""

    message: str
