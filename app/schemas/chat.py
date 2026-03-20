# app/schemas/chat.py
"""聊天相关的 Pydantic schemas"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ChatMessageCreate(BaseModel):
    """创建聊天消息的请求"""

    content: str = Field(..., min_length=1, max_length=5000, description="消息内容")


class ChatMessageResponse(BaseModel):
    """聊天消息响应"""

    id: int
    role: str
    content: str
    created_at: datetime
    metadata: Optional[dict] = None

    class Config:
        from_attributes = True


class ChatSessionCreate(BaseModel):
    """创建会话的请求（可选，通常为空）"""

    title: Optional[str] = Field(None, max_length=200, description="会话标题")


class ChatSessionResponse(BaseModel):
    """聊天会话响应"""

    session_id: str
    title: Optional[str]
    source: str = "web"  # 会话来源：web, feishu
    username: Optional[str] = None  # Web 用户名
    external_user_name: Optional[str] = None  # 飞书用户名
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_message: Optional[str] = None

    class Config:
        from_attributes = True


class ChatSessionListResponse(BaseModel):
    """会话列表响应"""

    sessions: List[ChatSessionResponse]
    total: int
