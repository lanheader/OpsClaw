"""提示词管理 API 端点"""

import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.models.agent_prompt import AgentPrompt, PromptVersion
from app.core.deps import get_current_admin
from app.schemas.agent_prompt import (
    AgentPromptCreate,
    AgentPromptUpdate,
    AgentPromptResponse,
    AgentPromptListItem,
    PromptVersionResponse,
    PromptVersionListItem,
    RollbackRequest,
    RollbackResponse,
    ClearCacheResponse,
)
from app.services.unified_prompt_optimizer import get_prompt_optimizer

router = APIRouter(prefix="/prompts", tags=["prompts"])
logger = logging.getLogger(__name__)


# ========== 列表和详情 ==========

@router.get("", response_model=List[AgentPromptListItem])
async def get_all_prompts(  # type: ignore[no-untyped-def]
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """获取所有提示词配置（列表视图，不含完整内容）"""
    prompts = db.query(AgentPrompt).order_by(AgentPrompt.agent_name).all()

    result = []
    for p in prompts:
        item = AgentPromptListItem(
            id=p.id,  # type: ignore[arg-type]
            agent_name=p.agent_name,  # type: ignore[arg-type]
            name=p.name,  # type: ignore[arg-type]
            description=p.description,  # type: ignore[arg-type]
            version=p.version,  # type: ignore[arg-type]
            is_active=p.is_active,  # type: ignore[arg-type]
            content_preview=p.content[:200] + "..." if len(p.content) > 200 else p.content,  # type: ignore[arg-type]
            created_at=p.created_at,  # type: ignore[arg-type]
            updated_at=p.updated_at,  # type: ignore[arg-type]
        )
        result.append(item)

    return result


@router.get("/{agent_name}", response_model=AgentPromptResponse)
async def get_prompt(  # type: ignore[no-untyped-def]
    agent_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """获取指定 Agent 的提示词（完整内容）"""
    prompt = db.query(AgentPrompt).filter(AgentPrompt.agent_name == agent_name).first()
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"提示词不存在: {agent_name}"
        )
    return AgentPromptResponse.model_validate(prompt)


# ========== 创建和更新 ==========

@router.post("", response_model=AgentPromptResponse, status_code=status.HTTP_201_CREATED)
async def create_prompt(  # type: ignore[no-untyped-def]
    data: AgentPromptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """创建新的提示词"""
    # 检查是否已存在
    existing = db.query(AgentPrompt).filter(AgentPrompt.agent_name == data.agent_name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"提示词已存在: {data.agent_name}"
        )

    # 创建提示词
    new_prompt = AgentPrompt(
        agent_name=data.agent_name,
        name=data.name,
        description=data.description,
        content=data.content,
        version=1,
        is_active=True,
    )
    db.add(new_prompt)
    db.flush()

    # 创建初始版本记录
    version_record = PromptVersion(
        prompt_id=new_prompt.id,
        agent_name=new_prompt.agent_name,
        version=1,
        content=new_prompt.content,
        change_summary="初始版本",
        changed_by=current_user.username,
    )
    db.add(version_record)

    db.commit()
    db.refresh(new_prompt)

    logger.info(f"Admin {current_user.username} created prompt: {data.agent_name}")
    return AgentPromptResponse.model_validate(new_prompt)


@router.put("/{agent_name}", response_model=AgentPromptResponse)
async def update_prompt(  # type: ignore[no-untyped-def]
    agent_name: str,
    data: AgentPromptUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """更新提示词（自动创建版本记录）"""
    prompt = db.query(AgentPrompt).filter(AgentPrompt.agent_name == agent_name).first()
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"提示词不存在: {agent_name}"
        )

    # 检查是否有内容变更
    old_content = prompt.content
    update_data = data.model_dump(exclude_unset=True)

    # 更新字段
    for field, value in update_data.items():
        setattr(prompt, field, value)

    # 如果内容有变更，增加版本号并创建版本记录
    if "content" in update_data and update_data["content"] != old_content:
        prompt.version += 1  # type: ignore[assignment]

        # 创建版本记录
        version_record = PromptVersion(
            prompt_id=prompt.id,
            agent_name=prompt.agent_name,
            version=prompt.version,
            content=prompt.content,
            change_summary=f"Version {prompt.version}",
            changed_by=current_user.username,
        )
        db.add(version_record)

    db.commit()
    db.refresh(prompt)

    # 清除缓存
    optimizer = get_prompt_optimizer()
    optimizer.clear_cache(agent_name)

    logger.info(f"Admin {current_user.username} updated prompt: {agent_name} to version {prompt.version}")
    return AgentPromptResponse.model_validate(prompt)


# ========== 版本管理 ==========

@router.get("/{agent_name}/versions", response_model=List[PromptVersionListItem])
async def get_prompt_versions(  # type: ignore[no-untyped-def]
    agent_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """获取提示词的版本历史"""
    versions = (
        db.query(PromptVersion)
        .filter(PromptVersion.agent_name == agent_name)
        .order_by(PromptVersion.version.desc())
        .all()
    )

    result = []
    for v in versions:
        item = PromptVersionListItem(
            id=v.id,  # type: ignore[arg-type]
            prompt_id=v.prompt_id,  # type: ignore[arg-type]
            agent_name=v.agent_name,  # type: ignore[arg-type]
            version=v.version,  # type: ignore[arg-type]
            content_preview=v.content[:200] + "..." if len(v.content) > 200 else v.content,  # type: ignore[arg-type]
            change_summary=v.change_summary,  # type: ignore[arg-type]
            changed_by=v.changed_by,  # type: ignore[arg-type]
            created_at=v.created_at,  # type: ignore[arg-type]
        )
        result.append(item)

    return result


@router.get("/{agent_name}/versions/{version}", response_model=PromptVersionResponse)
async def get_prompt_version_content(  # type: ignore[no-untyped-def]
    agent_name: str,
    version: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """获取指定版本的完整内容"""
    version_record = (
        db.query(PromptVersion)
        .filter(
            PromptVersion.agent_name == agent_name,
            PromptVersion.version == version
        )
        .first()
    )
    if not version_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"版本不存在: {agent_name} v{version}"
        )
    return PromptVersionResponse.model_validate(version_record)


@router.post("/{agent_name}/rollback", response_model=RollbackResponse)
async def rollback_prompt(  # type: ignore[no-untyped-def]
    agent_name: str,
    data: RollbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """回滚提示词到指定版本"""
    prompt = db.query(AgentPrompt).filter(AgentPrompt.agent_name == agent_name).first()
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"提示词不存在: {agent_name}"
        )

    # 查找目标版本
    target_version = (
        db.query(PromptVersion)
        .filter(
            PromptVersion.agent_name == agent_name,
            PromptVersion.version == data.target_version
        )
        .first()
    )
    if not target_version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"版本 {data.target_version} 不存在"
        )

    # 回滚内容
    old_version = prompt.version
    prompt.content = target_version.content
    prompt.version = data.target_version  # type: ignore[assignment]

    # 创建回滚版本记录
    rollback_record = PromptVersion(
        prompt_id=prompt.id,
        agent_name=prompt.agent_name,
        version=prompt.version,
        content=prompt.content,
        change_summary=f"从 v{old_version} 回滚到 v{data.target_version}",
        changed_by=current_user.username,
    )
    db.add(rollback_record)

    db.commit()
    db.refresh(prompt)

    # 清除缓存
    optimizer = get_prompt_optimizer()
    optimizer.clear_cache(agent_name)

    logger.info(f"Admin {current_user.username} rolled back {agent_name} to version {data.target_version}")

    return RollbackResponse(
        success=True,
        message=f"成功回滚到版本 {data.target_version}",
        current_version=prompt.version  # type: ignore[arg-type]
    )


# ========== 缓存管理 ==========

@router.post("/clear-cache", response_model=ClearCacheResponse)
async def clear_cache(  # type: ignore[no-untyped-def]
    current_user: User = Depends(get_current_admin)
):
    """清除所有提示词缓存"""
    optimizer = get_prompt_optimizer()
    optimizer.clear_cache()
    logger.info(f"Admin {current_user.username} cleared all prompt cache")

    return ClearCacheResponse(message="缓存已清除")
