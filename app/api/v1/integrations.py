# app/api/v1/integrations.py
"""外部系统集成测试 API 端点"""

import logging
import time
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.models.system_setting import SystemSetting
from app.core.deps import get_current_admin
from app.core.config import get_settings
from app.core.integration_config import IntegrationConfig

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
    """测试 Kubernetes 连接"""
    settings = get_settings()

    if not settings.K8S_ENABLED:
        return IntegrationTestResponse(
            success=False, service="kubernetes", error="Kubernetes 未启用"
        )

    try:
        from kubernetes import client, config
        import os

        start_time = time.time()

        # 加载 kubeconfig
        if settings.KUBECONFIG and os.path.exists(settings.KUBECONFIG):
            config.load_kube_config(config_file=settings.KUBECONFIG)
        else:
            config.load_kube_config()

        # 创建 API 客户端
        v1 = client.CoreV1Api()

        # 测试连接 - 获取版本信息
        version_api = client.VersionApi()
        version_info = version_api.get_code()

        # 获取节点数量
        nodes = v1.list_node()
        node_count = len(nodes.items)

        end_time = time.time()
        response_time_ms = (end_time - start_time) * 1000

        logger.info(
            f"Admin {current_user.username} tested Kubernetes connection, response_time={response_time_ms:.2f}ms"
        )

        return IntegrationTestResponse(
            success=True,
            service="kubernetes",
            response_time_ms=round(response_time_ms, 2),
            version=version_info.git_version,
            details={
                "node_count": node_count,
                "platform": version_info.platform,
            },
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
        import httpx

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
        import httpx

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
        from app.integrations.feishu.client import FeishuClient

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
