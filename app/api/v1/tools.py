"""
工具权限管理 API

提供工具分组、工具详情和用户可用工具的查询接口。
支持两级权限控制（分组 + 工具级）。
"""

import logging
from typing import List, Dict, Optional, Set
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.models.database import get_db
from app.models.user import User
from app.core.deps import get_current_user
from app.core.permission_checker import get_user_permission_codes
from app.tools.registry import get_tool_registry, ToolGroup, ToolPermission
from app.tools.base import BaseOpTool, ToolMetadata

router = APIRouter(prefix="/tools", tags=["tools"])
logger = logging.getLogger(__name__)


class ToolGroupResponse(BaseModel):
    """工具分组响应"""
    code: str
    name: str
    category: str
    operation_type: str
    description: str
    tool_count: int
    tools: List[str]  # 工具名称列表


class ToolDetailResponse(BaseModel):
    """工具详情响应"""
    name: str
    group: str
    operation_type: str
    risk_level: str
    permissions: List[str]
    description: str
    examples: List[str]
    enabled: bool
    expose_to_agent: bool


class ToolPermissionResponse(BaseModel):
    """工具权限响应"""
    code: str
    name: str
    description: str
    groups: List[str]


class UserToolsResponse(BaseModel):
    """用户可用工具响应"""
    groups: Dict[str, List[str]]  # 分组代码 -> 工具名称列表
    total_tools: int


# ========== API 端点 ==========

@router.get("/groups", response_model=List[ToolGroupResponse])
async def list_tool_groups(
    current_user: User = Depends(get_current_user),
):
    """
    获取所有工具分组

    返回工具分组的层级结构：
    - 第一级：工具模块（k8s, prometheus, loki）
    - 第二级：操作类型（read, write, delete, update）
    """
    registry = get_tool_registry()
    groups = registry.list_groups()

    result = []
    for group in groups:
        result.append(ToolGroupResponse(
            code=group.code,
            name=group.name,
            category=group.category.value,
            operation_type=group.operation_type.value,
            description=group.description,
            tool_count=len(group.tools),
            tools=group.list_tools()
        ))

    return result


@router.get("/groups/{group_code}", response_model=ToolGroupResponse)
async def get_tool_group(
    group_code: str,
    current_user: User = Depends(get_current_user),
):
    """获取指定工具分组的详情"""
    registry = get_tool_registry()
    group = registry.get_group(group_code)

    if not group:
        raise HTTPException(status_code=404, detail=f"Group {group_code} not found")

    return ToolGroupResponse(
        code=group.code,
        name=group.name,
        category=group.category.value,
        operation_type=group.operation_type.value,
        description=group.description,
        tool_count=len(group.tools),
        tools=group.list_tools()
    )


@router.get("/groups/{group_code}/tools", response_model=List[ToolDetailResponse])
async def list_group_tools(
    group_code: str,
    current_user: User = Depends(get_current_user),
):
    """获取指定分组下的所有工具详情"""
    registry = get_tool_registry()
    tools = registry.list_tools(group_code)

    result = []
    for tool_class in tools:
        metadata = tool_class.get_metadata()
        if metadata:
            result.append(ToolDetailResponse(
                name=metadata.name,
                group=metadata.group,
                operation_type=metadata.operation_type.value,
                risk_level=metadata.risk_level.value,
                permissions=metadata.permissions,
                description=metadata.description,
                examples=metadata.examples,
                enabled=metadata.enabled,
                expose_to_agent=metadata.expose_to_agent
            ))

    return result


@router.get("/tools/{tool_name}", response_model=ToolDetailResponse)
async def get_tool_detail(
    tool_name: str,
    current_user: User = Depends(get_current_user),
):
    """获取指定工具的详情"""
    registry = get_tool_registry()
    tool_class = registry.get_tool(tool_name)

    if not tool_class:
        raise HTTPException(status_code=404, detail=f"Tool {tool_name} not found")

    metadata = tool_class.get_metadata()
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Tool {tool_name} has no metadata")

    return ToolDetailResponse(
        name=metadata.name,
        group=metadata.group,
        operation_type=metadata.operation_type.value,
        risk_level=metadata.risk_level.value,
        permissions=metadata.permissions,
        description=metadata.description,
        examples=metadata.examples,
        enabled=metadata.enabled,
        expose_to_agent=metadata.expose_to_agent
    )


@router.get("/permissions", response_model=List[ToolPermissionResponse])
async def list_tool_permissions(
    current_user: User = Depends(get_current_user),
):
    """获取所有工具权限定义"""
    registry = get_tool_registry()
    permissions = registry.get_permissions()

    result = []
    for perm in permissions:
        result.append(ToolPermissionResponse(
            code=perm.code,
            name=perm.name,
            description=perm.description,
            groups=perm.groups
        ))

    return result


@router.get("/my", response_model=UserToolsResponse)
async def get_my_tools(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    获取当前用户可用的工具列表

    根据用户的权限过滤可用的工具。
    返回按分组组织的工具列表。
    """
    # 获取用户权限
    user_permissions = set(get_user_permission_codes(db, current_user.id))

    # 获取工具注册表
    registry = get_tool_registry()

    # 过滤用户可用的工具
    tools_by_group: Dict[str, List[str]] = {}
    total_tools = 0

    for group in registry.list_groups():
        group_tools = []

        for tool_name, tool_class in group.tools.items():
            metadata = tool_class.get_metadata()

            if not metadata:
                continue

            # 检查工具是否启用
            if not metadata.enabled:
                continue

            # 检查工具是否暴露给 agent
            if not metadata.expose_to_agent:
                continue

            # 检查用户是否有权限
            required_perms = set(metadata.permissions)
            if required_perms and not required_perms.issubset(user_permissions):
                continue

            group_tools.append(tool_name)
            total_tools += 1

        if group_tools:
            tools_by_group[group.code] = group_tools

    return UserToolsResponse(
        groups=tools_by_group,
        total_tools=total_tools
    )


@router.post("/reload")
async def reload_tools(
    current_user: User = Depends(get_current_user),
):
    """
    重新加载工具注册表

    扫描并注册所有工具类，用于开发调试。
    生产环境建议禁用此端点。
    """
    # 检查用户是否有管理员权限
    # TODO: 添加管理员权限检查

    registry = get_tool_registry()
    registry.scan_and_register()

    return {
        "success": True,
        "message": "Tool registry reloaded",
        "tool_count": len(registry.list_tools()),
        "group_count": len(registry.list_groups())
    }


__all__ = [
    "router",
    "ToolGroupResponse",
    "ToolDetailResponse",
    "ToolPermissionResponse",
    "UserToolsResponse",
]
