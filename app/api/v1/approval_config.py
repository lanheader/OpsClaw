"""审批配置管理 API"""

from typing import List, Optional, Set
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin
from app.models.database import get_db
from app.models.approval_config import ApprovalConfig
from app.models.user import User
from app.services.approval_config_service import ApprovalConfigService
from app.tools import get_available_packages
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/approval-config", tags=["审批配置"])

class ToolApprovalConfig(BaseModel):
    """工具审批配置"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tool_name: str
    tool_group: Optional[str]
    risk_level: Optional[str]
    requires_approval: bool
    approval_roles: Optional[List[str]]
    exempt_roles: Optional[List[str]]
    description: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]


class SyncToolsResponse(BaseModel):
    """同步工具响应"""
    synced_count: int
    total_count: int


class BatchUpdateRequest(BaseModel):
    """批量更新请求"""
    tool_names: List[str]
    requires_approval: bool


class BatchUpdateResponse(BaseModel):
    """批量更新响应"""
    updated_count: int

@router.post("/sync", response_model=SyncToolsResponse)
async def sync_tools(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    同步工具到配置表

    从 ToolRegistry 扫描所有工具并同步到 approval_configs 表。
    新工具会被添加，现有工具会被更新（保留手动配置的审批状态）。
    会强制重新扫描工具目录以发现新工具。
    """
    try:
        # 强制重新扫描工具目录
        from app.tools.registry import get_tool_registry
        registry = get_tool_registry()
        registry.scan_and_register()

        synced_count = ApprovalConfigService.sync_tools_to_db(db)

        # 获取总工具数
        total_count = db.query(ApprovalConfig).count()

        logger.info(
            f"用户 {current_user.username} 同步工具配置: 新增 {synced_count}, 总计 {total_count}"
        )

        return SyncToolsResponse(synced_count=synced_count, total_count=total_count)

    except Exception as e:
        logger.error(f"同步工具配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")


@router.get("/tools", response_model=List[ToolApprovalConfig])
async def get_approval_tools(
    group: Optional[str] = Query(None, description="工具分组筛选"),
    risk_level: Optional[str] = Query(None, description="风险等级筛选 (low/medium/high)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    获取审批配置列表

    支持按工具分组和风险等级筛选。
    """
    try:
        configs = ApprovalConfigService.get_approval_config(
            db, group_code=group, risk_level=risk_level
        )
        logger.info(f"用户 {current_user.username} 获取审批配置列表: {len(configs)} 条")
        return configs

    except Exception as e:
        logger.error(f"获取审批配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.get("/packages", response_model=List[str])
async def get_available_packages(
    current_user: User = Depends(get_current_admin),
):
    """获取可用的工具包列表（如 k8s, prometheus, loki）"""
    try:
        packages = get_available_packages()
        logger.info(f"用户 {current_user.username} 获取工具包列表: {len(packages)} 个")
        return packages

    except Exception as e:
        logger.error(f"获取工具包列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.get("/tools/groups", response_model=List[str])
async def get_approval_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """获取所有工具分组"""
    try:
        groups = ApprovalConfigService.get_approval_groups(db)
        logger.info(f"用户 {current_user.username} 获取工具分组: {len(groups)} 个")
        return groups

    except Exception as e:
        logger.error(f"获取工具分组失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.get("/tools/{tool_name}", response_model=ToolApprovalConfig)
async def get_tool_config(
    tool_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """获取单个工具的审批配置"""
    try:
        config = ApprovalConfigService.get_tool_config(db, tool_name)
        if not config:
            raise HTTPException(status_code=404, detail=f"工具不存在: {tool_name}")
        logger.info(f"用户 {current_user.username} 获取工具配置: {tool_name}")
        return config

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取工具配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.put("/tools/{tool_name}")
async def update_tool_approval(
    tool_name: str,
    requires_approval: bool = Query(..., description="是否需要审批"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    更新工具审批状态

    设置指定工具是否需要审批。
    """
    try:
        success = ApprovalConfigService.set_tool_approval_enabled(
            db, tool_name, requires_approval
        )
        if not success:
            raise HTTPException(status_code=404, detail=f"工具不存在: {tool_name}")

        logger.info(
            f"用户 {current_user.username} 更新工具审批状态: {tool_name} -> {requires_approval}"
        )

        return {
            "success": True,
            "tool_name": tool_name,
            "requires_approval": requires_approval,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新工具审批状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.put("/tools/batch", response_model=BatchUpdateResponse)
async def batch_update_approval(
    request: BatchUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    批量更新工具审批状态

    批量设置多个工具的审批状态。
    """
    try:
        updated_count = ApprovalConfigService.batch_update_approval(
            db, request.tool_names, request.requires_approval
        )

        logger.info(
            f"用户 {current_user.username} 批量更新审批状态: "
            f"{updated_count} 个工具 -> {request.requires_approval}"
        )

        return BatchUpdateResponse(updated_count=updated_count)

    except Exception as e:
        logger.error(f"批量更新审批状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量更新失败: {str(e)}")


@router.get("/require-approval", response_model=List[str])
async def get_tools_require_approval(
    user_role: Optional[str] = Query(None, description="用户角色（用于角色豁免检查）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    获取需要审批的工具列表

    返回当前需要审批的工具名称集合（考虑角色豁免）。
    """
    try:
        tools = ApprovalConfigService.get_tools_require_approval(db, user_role=user_role)
        logger.info(f"用户 {current_user.username} 获取需要审批的工具: {len(tools)} 个")
        return list(tools)

    except Exception as e:
        logger.error(f"获取需要审批的工具列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")
