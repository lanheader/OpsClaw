# app/api/v1/llm.py
"""LLM 连接测试 API 端点"""

import logging
import time
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.core.deps import get_current_admin
from app.core.config import get_settings
from app.core.llm_factory import LLMFactory

router = APIRouter(prefix="/llm", tags=["llm"])
logger = logging.getLogger(__name__)


class LLMTestRequest(BaseModel):
    """LLM 测试请求"""

    provider: Literal["openai", "claude", "zhipu", "ollama"] = Field(
        ..., description="LLM 提供商"
    )


class LLMTestResponse(BaseModel):
    """LLM 测试响应"""

    success: bool
    provider: str
    model: Optional[str] = None
    response_time_ms: Optional[float] = None
    test_message: Optional[str] = None
    error: Optional[str] = None


@router.post("/test", response_model=LLMTestResponse)
async def test_llm_connection(
    request: LLMTestRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """测试 LLM 连接"""
    settings = get_settings()
    provider = request.provider

    # 检查提供商是否启用
    if provider == "openai" and not settings.OPENAI_API_KEY:
        return LLMTestResponse(success=False, provider=provider, error="OpenAI API Key 未配置")

    if provider == "claude" and not settings.CLAUDE_API_KEY:
        return LLMTestResponse(success=False, provider=provider, error="Claude API Key 未配置")

    if provider == "zhipu" and not settings.ZHIPU_API_KEY:
        return LLMTestResponse(success=False, provider=provider, error="智谱 API Key 未配置")

    if provider == "ollama" and not settings.OLLAMA_BASE_URL:
        return LLMTestResponse(success=False, provider=provider, error="Ollama Base URL 未配置")

    try:
        start_time = time.time()

        # 创建 LLM 实例
        llm = LLMFactory.create_llm(provider=provider)

        # 发送测试消息
        test_prompt = "请回复'连接成功'（只需要这4个字）"
        response = await llm.ainvoke(test_prompt)

        end_time = time.time()
        response_time_ms = (end_time - start_time) * 1000

        # 提取响应内容
        if hasattr(response, "content"):
            test_message = response.content
        else:
            test_message = str(response)

        # 获取模型名称
        model_name = None
        if provider == "openai":
            model_name = settings.OPENAI_MODEL
        elif provider == "claude":
            model_name = settings.CLAUDE_MODEL
        elif provider == "zhipu":
            model_name = settings.ZHIPU_MODEL
        elif provider == "ollama":
            model_name = settings.OLLAMA_MODEL

        logger.info(
            f"Admin {current_user.username} tested {provider} LLM, response_time={response_time_ms:.2f}ms"
        )

        return LLMTestResponse(
            success=True,
            provider=provider,
            model=model_name,
            response_time_ms=round(response_time_ms, 2),
            test_message=test_message[:100],  # 限制长度
        )

    except Exception as e:
        logger.error(f"{provider} LLM test error: {str(e)}")
        return LLMTestResponse(success=False, provider=provider, error=f"连接失败: {str(e)}")
