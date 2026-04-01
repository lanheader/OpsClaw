# app/schemas/onboarding.py
"""初始化引导相关的 Pydantic 模型"""

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
import re


class OnboardingStatusResponse(BaseModel):
    """初始化状态响应模型"""

    initialized: bool = Field(..., description="是否已完成初始化")
    step: int = Field(..., ge=0, le=4, description="当前步骤（0=未开始，1-4=对应步骤）")


class Step1Request(BaseModel):
    """Step 1: 账户设置请求模型"""

    password: str = Field(..., min_length=8, description="新密码（最少8个字符）")
    email: EmailStr = Field(..., description="邮箱地址")
    feishu_user_id: str = Field(..., min_length=1, description="飞书用户ID")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """验证密码强度"""
        if not re.search(r"[a-zA-Z]", v):
            raise ValueError("密码必须包含至少一个字母")
        if not re.search(r"\d", v):
            raise ValueError("密码必须包含至少一个数字")
        return v


class K8sConfigRequest(BaseModel):
    """Kubernetes 配置请求模型"""

    enabled: bool = Field(default=False, description="是否启用")
    api_host: Optional[str] = Field(None, description="Kubernetes API 地址")
    auth_mode: Optional[str] = Field(None, description="认证方式：kubeconfig 或 token")
    kubeconfig: Optional[str] = Field(None, description="Kubeconfig 内容（JSON）")
    token: Optional[str] = Field(None, description="Bearer Token")


class Step2Request(K8sConfigRequest):
    """Step 2: Kubernetes 配置请求模型"""

    pass


class PrometheusConfigRequest(BaseModel):
    """Prometheus 配置请求模型"""

    enabled: bool = Field(default=False, description="是否启用")
    url: Optional[str] = Field(None, description="Prometheus URL")


class Step3Request(PrometheusConfigRequest):
    """Step 3: Prometheus 配置请求模型"""

    pass


class LokiConfigRequest(BaseModel):
    """Loki 配置请求模型"""

    enabled: bool = Field(default=False, description="是否启用")
    url: Optional[str] = Field(None, description="Loki URL")


class Step4Request(LokiConfigRequest):
    """Step 4: Loki 配置请求模型"""

    pass


class OnboardingSummaryResponse(BaseModel):
    """初始化完成摘要响应模型"""

    account_configured: bool = Field(..., description="账户是否已配置")
    k8s_enabled: bool = Field(..., description="Kubernetes 是否启用")
    prometheus_enabled: bool = Field(..., description="Prometheus 是否启用")
    loki_enabled: bool = Field(..., description="Loki 是否启用")
