# app/api/v1/integrations.py
"""外部系统集成测试 API 端点"""

import logging
import os
import time
import tempfile
from typing import Optional, Dict, Any, Literal
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.models.system_setting import SystemSetting
from app.core.deps import get_current_admin
from app.core.config import get_settings
from app.core.integration_config import IntegrationConfig
from app.schemas.kubernetes_config import (
    KubernetesConfigResponse,
    KubernetesConfigUpdate,
    KubernetesConnectionTestRequest,
    KubernetesConnectionTestResponse,
)

from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
import httpx
from app.integrations.feishu.client import FeishuClient

router = APIRouter(prefix="/integrations", tags=["integrations"])
logger = logging.getLogger(__name__)


class IntegrationTestResponse(BaseModel):
    """集成测试响应"""

    success: bool
    service: str
    response_time_ms: Optional[float] = None
    version: Optional[str] = None
    details: Optional[dict] = None
    error: Optional[str] = None


@router.post("/test/kubernetes", response_model=IntegrationTestResponse)
async def test_kubernetes_connection(
    current_user: User = Depends(get_current_admin), db: Session = Depends(get_db)
):
    """测试 Kubernetes 连接（使用数据库配置）"""
    try:
        from app.integrations.kubernetes.client import create_client

        start_time = time.time()

        # 从数据库配置创建客户端
        k8s_client_instance = create_client(db=db)

        # 检查健康状态
        health = await k8s_client_instance.check_kubernetes_health()

        end_time = time.time()
        response_time_ms = (end_time - start_time) * 1000

        if health["healthy"]:
            # 获取节点数量
            try:
                nodes = k8s_client_instance.core_v1.list_node()
                node_count = len(nodes.items)
            except Exception:
                node_count = 0

            logger.info(
                f"Admin {current_user.username} tested Kubernetes connection, response_time={response_time_ms:.2f}ms"
            )

            return IntegrationTestResponse(
                success=True,
                service="kubernetes",
                response_time_ms=round(response_time_ms, 2),
                version=health.get("server_version", "unknown"),
                details={
                    "node_count": node_count,
                    "platform": health.get("platform", "unknown"),
                    "git_version": health.get("git_version", "unknown"),
                },
            )
        else:
            return IntegrationTestResponse(
                success=False,
                service="kubernetes",
                error=health.get("error", "Unknown error")
            )

    except Exception as e:
        logger.error(f"Kubernetes test error: {str(e)}")
        return IntegrationTestResponse(
            success=False, service="kubernetes", error=f"连接失败: {str(e)}"
        )


@router.post("/test/prometheus", response_model=IntegrationTestResponse)
async def test_prometheus_connection(
    current_user: User = Depends(get_current_admin), db: Session = Depends(get_db)
):
    """测试 Prometheus 连接"""
    settings = get_settings()

    if not settings.PROMETHEUS_ENABLED:
        return IntegrationTestResponse(
            success=False, service="prometheus", error="Prometheus 未启用"
        )

    if not settings.PROMETHEUS_URL:
        return IntegrationTestResponse(
            success=False, service="prometheus", error="Prometheus URL 未配置"
        )

    try:
        start_time = time.time()

        # 测试连接 - 获取版本信息
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 测试 /api/v1/status/buildinfo 端点
            response = await client.get(f"{settings.PROMETHEUS_URL}/api/v1/status/buildinfo")
            response.raise_for_status()
            build_info = response.json()

            # 测试查询端点
            query_response = await client.get(
                f"{settings.PROMETHEUS_URL}/api/v1/query", params={"query": "up"}
            )
            query_response.raise_for_status()

        end_time = time.time()
        response_time_ms = (end_time - start_time) * 1000

        version = build_info.get("data", {}).get("version", "unknown")

        logger.info(
            f"Admin {current_user.username} tested Prometheus connection, response_time={response_time_ms:.2f}ms"
        )

        return IntegrationTestResponse(
            success=True,
            service="prometheus",
            response_time_ms=round(response_time_ms, 2),
            version=version,
            details={"url": settings.PROMETHEUS_URL, "status": "healthy"},
        )

    except Exception as e:
        logger.error(f"Prometheus test error: {str(e)}")
        return IntegrationTestResponse(
            success=False, service="prometheus", error=f"连接失败: {str(e)}"
        )


@router.post("/test/loki", response_model=IntegrationTestResponse)
async def test_loki_connection(
    current_user: User = Depends(get_current_admin), db: Session = Depends(get_db)
):
    """测试 Loki 连接"""
    settings = get_settings()

    if not settings.LOKI_ENABLED:
        return IntegrationTestResponse(success=False, service="loki", error="Loki 未启用")

    if not settings.LOKI_URL:
        return IntegrationTestResponse(success=False, service="loki", error="Loki URL 未配置")

    try:
        start_time = time.time()

        # 测试连接 - 获取标签
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 测试 /loki/api/v1/labels 端点
            response = await client.get(f"{settings.LOKI_URL}/loki/api/v1/labels")
            response.raise_for_status()
            labels_data = response.json()

            # 测试查询端点
            query_response = await client.get(
                f"{settings.LOKI_URL}/loki/api/v1/query_range",
                params={"query": '{job=""}', "limit": 1},
            )
            query_response.raise_for_status()

        end_time = time.time()
        response_time_ms = (end_time - start_time) * 1000

        label_count = len(labels_data.get("data", []))

        logger.info(
            f"Admin {current_user.username} tested Loki connection, response_time={response_time_ms:.2f}ms"
        )

        return IntegrationTestResponse(
            success=True,
            service="loki",
            response_time_ms=round(response_time_ms, 2),
            details={"url": settings.LOKI_URL, "label_count": label_count, "status": "healthy"},
        )

    except Exception as e:
        logger.error(f"Loki test error: {str(e)}")
        return IntegrationTestResponse(success=False, service="loki", error=f"连接失败: {str(e)}")


@router.post("/test/feishu", response_model=IntegrationTestResponse)
async def test_feishu_connection(
    current_user: User = Depends(get_current_admin), db: Session = Depends(get_db)
):
    """测试飞书连接"""
    settings = get_settings()

    if not settings.FEISHU_ENABLED:
        return IntegrationTestResponse(success=False, service="feishu", error="飞书未启用")

    if not settings.FEISHU_APP_ID or not settings.FEISHU_APP_SECRET:
        return IntegrationTestResponse(
            success=False, service="feishu", error="飞书 APP_ID 或 APP_SECRET 未配置"
        )

    try:
        start_time = time.time()

        # 创建飞书客户端
        feishu_client = FeishuClient(
            app_id=settings.FEISHU_APP_ID, app_secret=settings.FEISHU_APP_SECRET
        )

        # 测试获取 access token
        token = await feishu_client.get_tenant_access_token()

        if not token:
            raise ValueError("无法获取 access token")

        end_time = time.time()
        response_time_ms = (end_time - start_time) * 1000

        logger.info(
            f"Admin {current_user.username} tested Feishu connection, response_time={response_time_ms:.2f}ms"
        )

        return IntegrationTestResponse(
            success=True,
            service="feishu",
            response_time_ms=round(response_time_ms, 2),
            details={
                "app_id": settings.FEISHU_APP_ID,
                "connection_mode": settings.FEISHU_CONNECTION_MODE,
                "status": "healthy",
            },
        )

    except Exception as e:
        logger.error(f"Feishu test error: {str(e)}")
        return IntegrationTestResponse(success=False, service="feishu", error=f"连接失败: {str(e)}")


# ========== 集成配置管理 ==========

class IntegrationConfigResponse(BaseModel):
    """集成配置响应"""

    k8s: Dict[str, Any]
    prometheus: Dict[str, Any]
    loki: Dict[str, Any]
    feishu: Optional[Dict[str, Any]] = None


class ToggleIntegrationRequest(BaseModel):
    """切换集成开关请求"""

    service: str = Field(..., description="服务名称: k8s, prometheus, loki")
    enabled: bool = Field(..., description="是否启用")


class ToggleIntegrationResponse(BaseModel):
    """切换集成开关响应"""

    success: bool
    service: str
    enabled: bool
    message: str


@router.get("/config", response_model=IntegrationConfigResponse)
async def get_integration_config(
    current_user: User = Depends(get_current_admin), db: Session = Depends(get_db)
):
    """
    获取集成配置

    返回所有集成的开关状态和配置信息。
    """
    try:
        config = IntegrationConfig.get_config_dict(db)

        # 添加飞书配置（从 settings 读取）
        settings = get_settings()
        config["feishu"] = {
            "enabled": settings.FEISHU_ENABLED,
            "app_id": settings.FEISHU_APP_ID,
            "connection_mode": settings.FEISHU_CONNECTION_MODE,
        }

        logger.info(f"Admin {current_user.username} retrieved integration config")
        return IntegrationConfigResponse(**config)

    except Exception as e:
        logger.error(f"Failed to get integration config: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取集成配置失败: {str(e)}"
        )


@router.post("/config/toggle", response_model=ToggleIntegrationResponse)
async def toggle_integration(
    request: ToggleIntegrationRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    切换集成开关

    支持的服务: k8s, prometheus, loki
    """
    valid_services = ["k8s", "prometheus", "loki"]

    if request.service not in valid_services:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的服务名称: {request.service}，支持: {', '.join(valid_services)}"
        )

    try:
        setting_key = f"{request.service}.enabled"

        # 查找现有设置
        setting = db.query(SystemSetting).filter(
            SystemSetting.key == setting_key
        ).first()

        if setting:
            # 更新现有设置
            setting.value = str(request.enabled).lower()
        else:
            # 创建新设置
            setting = SystemSetting(
                key=setting_key,
                value=str(request.enabled).lower(),
                value_type="boolean",
                description=f"{request.service.upper()} 集成开关"
            )
            db.add(setting)

        db.commit()

        logger.info(
            f"Admin {current_user.username} toggled {request.service} to {request.enabled}"
        )

        return ToggleIntegrationResponse(
            success=True,
            service=request.service,
            enabled=request.enabled,
            message=f"{request.service.upper()} 已{'启用' if request.enabled else '禁用'}"
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to toggle integration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"切换集成开关失败: {str(e)}"
        )


@router.get("/config/{service}", response_model=Dict[str, Any])
async def get_service_config(
    service: str,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    获取单个服务的配置

    支持的服务: k8s, prometheus, loki
    """
    valid_services = ["k8s", "prometheus", "loki"]

    if service not in valid_services:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的服务名称: {service}，支持: {', '.join(valid_services)}"
        )

    try:
        config = IntegrationConfig.get_config_dict(db)
        service_config = config.get(service, {})

        logger.info(f"Admin {current_user.username} retrieved {service} config")
        return service_config

    except Exception as e:
        logger.error(f"Failed to get {service} config: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取 {service} 配置失败: {str(e)}"
        )


# ========== Kubernetes 配置管理（专用端点）==========


def _mask_sensitive(value: Optional[str], show_length: int = 20) -> Optional[str]:
    """脱敏敏感信息"""
    if not value:
        return None
    if len(value) <= show_length:
        return value[:4] + "*" * (len(value) - 4)
    return value[:show_length] + "..."


@router.get("/kubernetes/config", response_model=KubernetesConfigResponse)
async def get_kubernetes_config(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    获取 Kubernetes 配置

    敏感字段会进行脱敏处理。
    """
    try:
        config = IntegrationConfig.get_config_dict(db)
        k8s_config_data = config.get("k8s", {})

        return KubernetesConfigResponse(
            enabled=k8s_config_data.get("enabled", False),
            auth_mode=k8s_config_data.get("auth_mode", "kubeconfig"),
            kubeconfig_content_masked=_mask_sensitive(k8s_config_data.get("kubeconfig")),
            api_host=k8s_config_data.get("api_host"),
            token_masked=_mask_sensitive(k8s_config_data.get("token")),
            ca_cert_masked=_mask_sensitive(k8s_config_data.get("ca_cert"), show_length=50),
        )

    except Exception as e:
        logger.error(f"Failed to get Kubernetes config: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取 Kubernetes 配置失败: {str(e)}"
        )


@router.put("/kubernetes/config", response_model=KubernetesConfigResponse)
async def update_kubernetes_config(
    data: KubernetesConfigUpdate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    更新 Kubernetes 配置

    支持两种认证模式：
    - kubeconfig: 将 kubeconfig 文件内容粘贴到 kubeconfig_content 字段
    - token: 提供 api_host、token 和可选的 ca_cert

    更新后会自动启用 K8s 集成。
    """
    try:
        # 更新配置项
        config_updates = {
            "k8s.enabled": (str(data.enabled).lower(), "boolean", "K8s 集成开关"),
            "k8s.auth_mode": (data.auth_mode, "string", "K8s 认证模式"),
        }

        # 根据认证模式更新对应的配置
        if data.auth_mode == "kubeconfig":
            if data.kubeconfig_content:
                config_updates["k8s.kubeconfig"] = (
                    data.kubeconfig_content,
                    "string",
                    "K8s kubeconfig 内容"
                )
        else:  # token 模式
            if data.api_host:
                config_updates["k8s.api_host"] = (
                    data.api_host,
                    "string",
                    "K8s API Server 地址"
                )
            if data.token:
                config_updates["k8s.token"] = (
                    data.token,
                    "string",
                    "K8s ServiceAccount Token"
                )
            if data.ca_cert:
                config_updates["k8s.ca_cert"] = (
                    data.ca_cert,
                    "string",
                    "K8s CA 证书"
                )

        # 批量更新配置
        for key, (value, value_type, description) in config_updates.items():
            setting = db.query(SystemSetting).filter(
                SystemSetting.key == key
            ).first()

            if setting:
                setting.value = value
            else:
                setting = SystemSetting(
                    key=key,
                    value=value,
                    value_type=value_type,
                    description=description,
                    category="kubernetes",
                    name=key.split(".")[-1],
                )
                db.add(setting)

        db.commit()

        logger.info(f"Admin {current_user.username} updated Kubernetes config (mode={data.auth_mode})")

        # 返回更新后的配置（脱敏）
        return await get_kubernetes_config(current_user, db)

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update Kubernetes config: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新 Kubernetes 配置失败: {str(e)}"
        )


@router.post("/kubernetes/test", response_model=KubernetesConnectionTestResponse)
async def test_kubernetes_config(
    request: Optional[KubernetesConnectionTestRequest] = None,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    测试 Kubernetes 连接

    如果不提供请求体，则使用数据库中保存的配置进行测试。
    如果提供请求体，则使用临时配置进行测试（不会保存到数据库）。
    """
    try:
        from app.integrations.kubernetes.client import KubernetesClient, create_client
        import time

        start_time = time.time()

        # 决定使用哪个配置
        if request and request.auth_mode:
            logger.info(f"Testing K8s with request config: auth_mode={request.auth_mode}")
            # 使用临时配置
            if request.auth_mode == "kubeconfig":
                if not request.kubeconfig_content:
                    return KubernetesConnectionTestResponse(
                        success=False,
                        message="kubeconfig 模式需要提供 kubeconfig_content"
                    )
                client = KubernetesClient(
                    auth_mode="kubeconfig",
                    kubeconfig_content=request.kubeconfig_content
                )
            else:  # token 模式
                if not request.token or not request.api_host:
                    return KubernetesConnectionTestResponse(
                        success=False,
                        message="token 模式需要提供 token 和 api_host"
                    )
                client = KubernetesClient(
                    auth_mode="token",
                    token=request.token,
                    api_host=request.api_host,
                    ca_cert=request.ca_cert
                )
        else:
            # 使用数据库配置
            logger.info("Testing K8s with database config")

            # 先检查配置
            enabled = IntegrationConfig.is_k8s_enabled(db)
            auth_mode = IntegrationConfig.get_k8s_auth_mode(db)
            logger.info(f"K8s config from DB: enabled={enabled}, auth_mode={auth_mode}")

            if not enabled:
                return KubernetesConnectionTestResponse(
                    success=False,
                    message="Kubernetes 集成未启用，请先在配置中启用"
                )

            if auth_mode == "token":
                api_host = IntegrationConfig.get_k8s_api_host(db)
                token = IntegrationConfig.get_k8s_token(db)
                ca_cert = IntegrationConfig.get_k8s_ca_cert(db)
                logger.info(f"Token mode: api_host={api_host}, has_token={bool(token)}, has_ca_cert={bool(ca_cert)}")

                if not api_host or not token:
                    return KubernetesConnectionTestResponse(
                        success=False,
                        message="token 模式需要配置 api_host 和 token"
                    )
            else:
                kubeconfig = IntegrationConfig.get_k8s_kubeconfig(db)
                logger.info(f"Kubeconfig mode: has_kubeconfig={bool(kubeconfig)}")

                if not kubeconfig:
                    return KubernetesConnectionTestResponse(
                        success=False,
                        message="kubeconfig 模式需要配置 kubeconfig 内容"
                    )

            client = create_client(db=db)

        # 执行健康检查
        health = await client.check_kubernetes_health()

        end_time = time.time()
        response_time_ms = (end_time - start_time) * 1000

        if health["healthy"]:
            logger.info(
                f"Admin {current_user.username} tested Kubernetes connection, "
                f"response_time={response_time_ms:.2f}ms"
            )

            return KubernetesConnectionTestResponse(
                success=True,
                message="Kubernetes 连接成功",
                cluster_info=f"Platform: {health.get('platform', 'unknown')}",
                server_version=health.get("server_version", "unknown"),
                response_time_ms=round(response_time_ms, 2),
            )
        else:
            return KubernetesConnectionTestResponse(
                success=False,
                message=f"Kubernetes 连接失败: {health.get('error', 'Unknown error')}",
                response_time_ms=round(response_time_ms, 2),
            )

    except Exception as e:
        logger.error(f"Kubernetes test error: {str(e)}")
        return KubernetesConnectionTestResponse(
            success=False,
            message=f"连接测试失败: {str(e)}"
        )
