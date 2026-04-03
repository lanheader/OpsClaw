# app/api/v1/settings.py
"""系统设置 API 端点"""

import json
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.models.system_setting import SystemSetting
from app.core.deps import get_current_admin
from app.schemas.system_setting import (
    SystemSettingCreate,
    SystemSettingUpdate,
    SystemSettingResponse,
    SystemSettingBatchUpdate,
)

router = APIRouter(prefix="/settings", tags=["settings"])
logger = logging.getLogger(__name__)


@router.get("", response_model=Dict[str, List[SystemSettingResponse]])
async def get_all_settings(  # type: ignore[no-untyped-def]
    db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)
):
    """获取所有系统设置（按分类分组）"""
    settings = db.query(SystemSetting).all()

    # 按分类分组
    grouped_settings: Dict[str, List[SystemSettingResponse]] = {}
    for setting in settings:
        category = setting.category
        if category not in grouped_settings:
            grouped_settings[category] = []  # type: ignore[index]

        # 如果是敏感信息，不返回实际值
        setting_dict = SystemSettingResponse.model_validate(setting)
        if setting.is_sensitive and setting.value:
            setting_dict.value = "******"

        grouped_settings[category].append(setting_dict)  # type: ignore[index]

    return grouped_settings


@router.get("/{key}", response_model=SystemSettingResponse)
async def get_setting(  # type: ignore[no-untyped-def]
    key: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)
):
    """获取单个系统设置"""
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not setting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"设置不存在: {key}")

    setting_dict = SystemSettingResponse.model_validate(setting)
    # 如果是敏感信息，不返回实际值
    if setting.is_sensitive and setting.value:
        setting_dict.value = "******"

    return setting_dict


@router.post("", response_model=SystemSettingResponse, status_code=status.HTTP_201_CREATED)
async def create_setting(  # type: ignore[no-untyped-def]
    setting_data: SystemSettingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """创建系统设置"""
    # 检查设置是否已存在
    existing = db.query(SystemSetting).filter(SystemSetting.key == setting_data.key).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"设置已存在: {setting_data.key}"
        )

    # 创建设置
    new_setting = SystemSetting(**setting_data.model_dump())
    db.add(new_setting)
    db.commit()
    db.refresh(new_setting)

    logger.info(f"Admin {current_user.username} created setting: {new_setting.key}")

    return SystemSettingResponse.model_validate(new_setting)


@router.put("/{key}", response_model=SystemSettingResponse)
async def update_setting(  # type: ignore[no-untyped-def]
    key: str,
    setting_data: SystemSettingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """更新系统设置"""
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not setting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"设置不存在: {key}")

    # 检查是否只读
    if setting.is_readonly:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"设置为只读，不可修改: {key}"
        )

    # 更新字段
    update_data = setting_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(setting, field, value)

    db.commit()
    db.refresh(setting)

    logger.info(f"Admin {current_user.username} updated setting: {key}")

    return SystemSettingResponse.model_validate(setting)


@router.post("/batch", response_model=Dict[str, str])
async def batch_update_settings(  # type: ignore[no-untyped-def]
    batch_data: SystemSettingBatchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """批量更新系统设置"""
    updated_count = 0
    errors = []

    for key, value in batch_data.settings.items():
        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if not setting:
            errors.append(f"设置不存在: {key}")
            continue

        if setting.is_readonly:
            errors.append(f"设置为只读: {key}")
            continue

        # 根据类型转换值
        if setting.value_type == "boolean":
            # 统一存 0/1
            if isinstance(value, bool):
                setting.value = "1" if value else "0"  # type: ignore[assignment]
            elif isinstance(value, str):
                setting.value = "1" if value.lower() in ("true", "1", "yes") else "0"  # type: ignore[assignment]
            else:
                setting.value = "1" if value else "0"  # type: ignore[assignment]
        elif setting.value_type == "json":
            setting.value = json.dumps(value, ensure_ascii=False)  # type: ignore[assignment]
        else:
            setting.value = str(value)  # type: ignore[assignment]

        updated_count += 1

    db.commit()

    logger.info(f"Admin {current_user.username} batch updated {updated_count} settings")

    return {
        "message": f"成功更新 {updated_count} 个设置",
        "errors": ", ".join(errors) if errors else "",
    }


@router.post("/init", response_model=Dict[str, str])
async def init_default_settings(  # type: ignore[no-untyped-def]
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    初始化默认系统设置（幂等，已存在则跳过）

    Prometheus 和 Loki 的开关类型为 boolean，值存 0/1。
    """
    defaults = [
        # Prometheus
        {
            "key": "prometheus.enabled",
            "value": "0",
            "value_type": "boolean",
            "category": "prometheus",
            "name": "启用 Prometheus",
            "description": "开启后可查询集群监控指标（CPU、内存等）",
        },
        {
            "key": "prometheus.url",
            "value": "http://localhost:9090",
            "value_type": "string",
            "category": "prometheus",
            "name": "Prometheus 地址",
            "description": "Prometheus 服务的 HTTP 地址",
        },
        # Loki
        {
            "key": "loki.enabled",
            "value": "0",
            "value_type": "boolean",
            "category": "loki",
            "name": "启用 Loki",
            "description": "开启后可查询集群日志",
        },
        {
            "key": "loki.url",
            "value": "http://localhost:3100",
            "value_type": "string",
            "category": "loki",
            "name": "Loki 地址",
            "description": "Loki 服务的 HTTP 地址",
        },
    ]

    created = 0
    for default in defaults:
        existing = db.query(SystemSetting).filter(
            SystemSetting.key == default["key"]
        ).first()
        if not existing:
            db.add(SystemSetting(**default))
            created += 1

    db.commit()

    logger.info(f"Admin {current_user.username} initialized {created} default settings")

    return {"message": f"初始化完成，新增 {created} 条默认设置"}


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_setting(  # type: ignore[no-untyped-def]
    key: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)
):
    """删除系统设置"""
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not setting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"设置不存在: {key}")

    # 检查是否只读
    if setting.is_readonly:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"设置为只读，不可删除: {key}"
        )

    db.delete(setting)
    db.commit()

    logger.info(f"Admin {current_user.username} deleted setting: {key}")

    return None
