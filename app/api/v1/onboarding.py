# app/api/v1/onboarding.py
"""初始化引导 API 端点"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.models.system_setting import SystemSetting
from app.core.deps import get_current_user
from app.core.security import hash_password
from app.schemas.onboarding import (
    OnboardingStatusResponse,
    Step1Request,
    Step2Request,
    Step3Request,
    Step4Request,
    OnboardingSummaryResponse,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
logger = logging.getLogger(__name__)

ONBOARDING_COMPLETED_KEY = "onboarding_completed"


def _get_or_create_setting(
    db: Session, key: str, default_value: str, category: str, name: str,
    value_type: str = "string", description: str = "", is_sensitive: bool = False
) -> SystemSetting:
    """获取或创建系统设置"""
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not setting:
        setting = SystemSetting(
            key=key,
            value=default_value,
            category=category,
            name=name,
            description=description,
            value_type=value_type,
            is_sensitive=is_sensitive,
        )
        db.add(setting)
    return setting


def _update_setting(db: Session, key: str, value: str) -> None:
    """更新系统设置值"""
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting:
        setting.value = value
    else:
        logger.warning(f"Setting not found: {key}")


@router.get("/status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """获取初始化状态"""
    # 检查是否已完成初始化
    completed_setting = db.query(SystemSetting).filter(
        SystemSetting.key == ONBOARDING_COMPLETED_KEY
    ).first()

    if completed_setting and completed_setting.value == "true":
        return OnboardingStatusResponse(initialized=True, step=4)

    # 检查当前步骤
    admin_user = db.query(User).filter(User.username == "admin").first()
    if not admin_user:
        # 没有 admin 用户，不允许初始化
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin 用户不存在"
        )

    # Step 1: 检查 admin 是否设置了邮箱和飞书ID
    if not admin_user.email or not admin_user.feishu_user_id:
        return OnboardingStatusResponse(initialized=False, step=1)

    # Step 2-4: 根据 system_settings 判断
    # 默认返回 step 2
    return OnboardingStatusResponse(initialized=False, step=2)


@router.post("/step1")
async def submit_step1(
    data: Step1Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Step 1: 账户设置 - 更新 admin 密码、邮箱、飞书ID"""
    # 只允许 admin 用户执行
    if current_user.username != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有 admin 用户可以执行初始化"
        )

    # 更新密码
    current_user.hashed_password = hash_password(data.password)

    # 更新邮箱
    # 检查邮箱是否已被其他用户使用
    existing_email = db.query(User).filter(
        User.email == data.email, User.id != current_user.id
    ).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱已被其他用户使用"
        )
    current_user.email = data.email

    # 更新飞书 ID
    # 检查飞书ID是否已被其他用户使用
    existing_feishu = db.query(User).filter(
        User.feishu_user_id == data.feishu_user_id, User.id != current_user.id
    ).first()
    if existing_feishu:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="飞书用户ID已被其他用户使用"
        )
    current_user.feishu_user_id = data.feishu_user_id

    db.commit()
    logger.info(f"Admin {current_user.username} completed step 1: account settings")

    return {"message": "账户设置已保存", "step": 1}


@router.post("/step2")
async def submit_step2(
    data: Step2Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Step 2: Kubernetes 配置"""
    # 只允许 admin 用户执行
    if current_user.username != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有 admin 用户可以执行初始化"
        )

    # 确保 K8s 设置存在
    k8s_settings = [
        ("k8s.enabled", "0" if not data.enabled else "1", "kubernetes", "启用 Kubernetes", "boolean", "开启后可管理 K8s 集群资源"),
        ("k8s.api_host", data.api_host or "", "kubernetes", "API 地址", "string", "Kubernetes API Server 地址"),
        ("k8s.auth_mode", data.auth_mode or "kubeconfig", "kubernetes", "认证方式", "string", "kubeconfig 或 token"),
        ("k8s.kubeconfig", data.kubeconfig or "", "kubernetes", "Kubeconfig", "json", "Kubeconfig 配置内容", True),
        ("k8s.token", data.token or "", "kubernetes", "Token", "string", "Bearer Token", True),
    ]

    for setting_data in k8s_settings:
        key, value, category, name, value_type, description = setting_data[:6]
        is_sensitive = setting_data[6] if len(setting_data) > 6 else False
        _get_or_create_setting(db, key, value, category, name, value_type, description, is_sensitive)
        _update_setting(db, key, value)

    db.commit()
    logger.info(f"Admin {current_user.username} completed step 2: Kubernetes config")

    return {"message": "Kubernetes 配置已保存", "step": 2}


@router.post("/step3")
async def submit_step3(
    data: Step3Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Step 3: Prometheus 配置"""
    # 只允许 admin 用户执行
    if current_user.username != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有 admin 用户可以执行初始化"
        )

    # 确保 Prometheus 设置存在
    prom_settings = [
        ("prometheus.enabled", "0" if not data.enabled else "1", "prometheus", "启用 Prometheus", "boolean", "开启后可查询集群监控指标"),
        ("prometheus.url", data.url or "http://localhost:9090", "prometheus", "Prometheus 地址", "string", "Prometheus 服务的 HTTP 地址"),
    ]

    for setting_data in prom_settings:
        key, value, category, name, value_type, description = setting_data
        _get_or_create_setting(db, key, value, category, name, value_type, description)
        _update_setting(db, key, value)

    db.commit()
    logger.info(f"Admin {current_user.username} completed step 3: Prometheus config")

    return {"message": "Prometheus 配置已保存", "step": 3}


@router.post("/step4")
async def submit_step4(
    data: Step4Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Step 4: Loki 配置"""
    # 只允许 admin 用户执行
    if current_user.username != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有 admin 用户可以执行初始化"
        )

    # 确保 Loki 设置存在
    loki_settings = [
        ("loki.enabled", "0" if not data.enabled else "1", "loki", "启用 Loki", "boolean", "开启后可查询集群日志"),
        ("loki.url", data.url or "http://localhost:3100", "loki", "Loki 地址", "string", "Loki 服务的 HTTP 地址"),
    ]

    for setting_data in loki_settings:
        key, value, category, name, value_type, description = setting_data
        _get_or_create_setting(db, key, value, category, name, value_type, description)
        _update_setting(db, key, value)

    db.commit()
    logger.info(f"Admin {current_user.username} completed step 4: Loki config")

    return {"message": "Loki 配置已保存", "step": 4}


@router.post("/complete", response_model=OnboardingSummaryResponse)
async def complete_onboarding(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """完成初始化"""
    # 只允许 admin 用户执行
    if current_user.username != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有 admin 用户可以执行初始化"
        )

    # 设置完成标记
    _get_or_create_setting(
        db, ONBOARDING_COMPLETED_KEY, "true", "system",
        "初始化完成", "boolean", "标记系统是否已完成初始化"
    )
    _update_setting(db, ONBOARDING_COMPLETED_KEY, "true")

    db.commit()
    logger.info(f"Admin {current_user.username} completed onboarding")

    # 返回配置摘要
    k8s_enabled = db.query(SystemSetting).filter(SystemSetting.key == "k8s.enabled").first()
    prom_enabled = db.query(SystemSetting).filter(SystemSetting.key == "prometheus.enabled").first()
    loki_enabled = db.query(SystemSetting).filter(SystemSetting.key == "loki.enabled").first()

    return OnboardingSummaryResponse(
        account_configured=True,
        k8s_enabled=k8s_enabled.value == "1" if k8s_enabled else False,
        prometheus_enabled=prom_enabled.value == "1" if prom_enabled else False,
        loki_enabled=loki_enabled.value == "1" if loki_enabled else False,
    )
