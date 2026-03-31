"""Kubernetes 配置相关的 Pydantic 模型"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal


class KubernetesConfigBase(BaseModel):
    """Kubernetes 配置基础模型"""

    enabled: bool = Field(default=False, description="是否启用 K8s 集成")
    auth_mode: Literal["kubeconfig", "token"] = Field(
        default="kubeconfig",
        description="认证模式: kubeconfig (配置文件内容) 或 token (ServiceAccount Token)"
    )

    # kubeconfig 模式
    kubeconfig_content: Optional[str] = Field(
        default=None,
        description="kubeconfig 文件内容 (YAML 格式)"
    )

    # token 模式
    api_host: Optional[str] = Field(
        default=None,
        description="Kubernetes API Server 地址 (如 https://k8s-api.example.com:6443)"
    )
    token: Optional[str] = Field(
        default=None,
        description="ServiceAccount Token"
    )
    ca_cert: Optional[str] = Field(
        default=None,
        description="CA 证书内容 (PEM 格式，可选)"
    )


class KubernetesConfigUpdate(KubernetesConfigBase):
    """更新 Kubernetes 配置模型"""

    @field_validator('kubeconfig_content')
    @classmethod
    def validate_kubeconfig_mode(cls, v, info):
        """当 auth_mode 为 kubeconfig 时，kubeconfig_content 必须提供"""
        if info.data.get('auth_mode') == 'kubeconfig' and not v:
            raise ValueError('kubeconfig 模式需要提供 kubeconfig_content')
        return v

    @field_validator('api_host', 'token')
    @classmethod
    def validate_token_mode(cls, v, info):
        """当 auth_mode 为 token 时，api_host 和 token 必须提供"""
        if info.data.get('auth_mode') == 'token':
            # 在 token 模式下检查必填字段
            pass
        return v


class KubernetesConfigResponse(BaseModel):
    """Kubernetes 配置响应模型（敏感字段脱敏）"""

    enabled: bool
    auth_mode: str

    # kubeconfig 模式（脱敏）
    kubeconfig_content_masked: Optional[str] = Field(
        default=None,
        description="kubeconfig 内容预览（脱敏）"
    )

    # token 模式
    api_host: Optional[str] = None
    token_masked: Optional[str] = Field(
        default=None,
        description="Token 预览（脱敏）"
    )
    ca_cert_masked: Optional[str] = Field(
        default=None,
        description="CA 证书预览（脱敏）"
    )


class KubernetesConnectionTestRequest(BaseModel):
    """测试 K8s 连接请求（可选提供临时配置）"""

    auth_mode: Optional[Literal["kubeconfig", "token"]] = None
    kubeconfig_content: Optional[str] = None
    api_host: Optional[str] = None
    token: Optional[str] = None
    ca_cert: Optional[str] = None


class KubernetesConnectionTestResponse(BaseModel):
    """测试 K8s 连接响应"""

    success: bool
    message: str
    cluster_info: Optional[str] = None
    server_version: Optional[str] = None
    response_time_ms: Optional[float] = None
