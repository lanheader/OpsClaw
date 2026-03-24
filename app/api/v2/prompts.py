"""
提示词管理 API 端点

提供 Web UI 管理提示词的接口
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_

from app.models.database import get_db
from app.models.user import User
from app.core.deps import get_current_user
from app.models.subagent_prompt import SubagentPrompt, PromptChangeLog
from app.services.prompt_management import PromptManagementService
from app.services.unified_prompt_optimizer import get_prompt_optimizer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/prompts", tags=["Prompts"])


# ==================== Pydantic 模型 ====================

class PromptListItem(BaseModel):
    """提示词列表项"""
    id: int
    subagent_name: str
    version: str
    prompt_type: str
    is_active: bool
    is_latest: bool
    content_preview: str
    notes: Optional[str] = None
    created_at: str
    updated_at: str


class PromptDetail(BaseModel):
    """提示词详情"""
    id: int
    subagent_name: str
    version: str
    prompt_type: str
    prompt_content: str
    is_active: bool
    is_latest: bool
    few_shot_examples: Optional[list] = None
    performance_score: float
    usage_count: int
    notes: Optional[str] = None
    created_at: str
    updated_at: str
    optimization_metadata: Optional[dict] = None


class UpdatePromptRequest(BaseModel):
    """更新提示词请求"""
    content: str = Field(..., description="提示词内容")
    notes: Optional[str] = Field(None, description="更新说明")


class PromptStatsResponse(BaseModel):
    """提示词统计响应"""
    total_prompts: int
    by_subagent: dict
    by_type: dict
    latest_versions: List[dict]


# ==================== 辅助函数 ====================

def _require_admin(user: User = Depends(get_current_user)):
    """要求管理员权限"""
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="需要管理员权限")


# ==================== API 端点 ====================

@router.get("/stats", response_model=PromptStatsResponse)
async def get_prompt_stats(
    user: User = Depends(get_current_user),
) -> PromptStatsResponse:
    """获取提示词统计信息"""
    from sqlalchemy import func

    db = next(get_db())
    try:
        # 总数统计
        total = db.query(SubagentPrompt).count()

        # 按 subagent 统计
        by_subagent = {}
        for name in ["data-agent", "analyze-agent", "execute-agent"]:
            count = (
                db.query(SubagentPrompt)
                .filter(SubagentPrompt.subagent_name == name)
                .count()
            )
            by_subagent[name] = count

        # 按类型统计
        by_type = {}
        for ptype in ["base", "optimized"]:
            count = (
                db.query(SubagentPrompt)
                .filter(SubagentPrompt.prompt_type == ptype)
                .count()
            )
            by_type[ptype] = count

        # 最新版本
        latest = (
            db.query(SubagentPrompt)
            .filter(SubagentPrompt.is_latest == True)
            .all()
        )
        latest_versions = [
            {
                "subagent_name": p.subagent_name,
                "version": p.version,
                "type": p.prompt_type,
                "is_active": p.is_active,
            }
            for p in latest
        ]

        return PromptStatsResponse(
            total_prompts=total,
            by_subagent=by_subagent,
            by_type=by_type,
            latest_versions=latest_versions,
        )

    finally:
        db.close()


@router.get("/list", response_model=List[PromptListItem])
async def list_prompts(
    subagent_name: Optional[str] = Query(None, description="过滤子智能体"),
    prompt_type: Optional[str] = Query(None, description="过滤类型: base, optimized"),
    user: User = Depends(get_current_user),
) -> List[PromptListItem]:
    """获取提示词列表"""
    service = PromptManagementService()
    prompts = service.list_all_prompts(subagent_name)

    # 按类型过滤
    if prompt_type:
        prompts = [p for p in prompts if p["prompt_type"] == prompt_type]

    return [PromptListItem(**p) for p in prompts]


@router.get("/logs")
async def get_change_logs(
    subagent_name: Optional[str] = Query(None, description="过滤子智能体"),
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
    user: User = Depends(get_current_user),
) -> dict:
    """获取提示词变更日志"""
    db = next(get_db())
    try:
        query = db.query(PromptChangeLog)

        if subagent_name:
            query = query.filter(PromptChangeLog.subagent_name == subagent_name)

        logs = (
            query.order_by(PromptChangeLog.changed_at.desc())
            .limit(limit)
            .all()
        )

        return {
            "total": len(logs),
            "logs": [
                {
                    "id": log.id,
                    "subagent_name": log.subagent_name,
                    "change_type": log.change_type,
                    "old_version": log.old_version,
                    "new_version": log.new_version,
                    "change_reason": log.change_reason,
                    "changed_at": log.changed_at.isoformat(),
                    "optimization_method": log.optimization_method,
                    "training_examples_count": log.training_examples_count,
                }
                for log in logs
            ],
        }

    finally:
        db.close()


@router.get("/{prompt_id}", response_model=PromptDetail)
async def get_prompt_detail(
    prompt_id: int,
    user: User = Depends(get_current_user),
) -> PromptDetail:
    """获取提示词详情"""
    db = next(get_db())
    try:
        prompt = db.query(SubagentPrompt).filter(SubagentPrompt.id == prompt_id).first()

        if not prompt:
            raise HTTPException(status_code=404, detail="提示词不存在")

        return PromptDetail(
            id=prompt.id,
            subagent_name=prompt.subagent_name,
            version=prompt.version,
            prompt_type=prompt.prompt_type,
            prompt_content=prompt.prompt_content,
            is_active=prompt.is_active,
            is_latest=prompt.is_latest,
            few_shot_examples=prompt.few_shot_examples,
            performance_score=prompt.performance_score,
            usage_count=prompt.usage_count,
            notes=prompt.notes,
            created_at=prompt.created_at.isoformat(),
            updated_at=prompt.updated_at.isoformat(),
            optimization_metadata=prompt.optimization_metadata,
        )

    finally:
        db.close()


@router.put("/{prompt_id}")
async def update_prompt(
    prompt_id: int,
    request: UpdatePromptRequest,
    user: User = Depends(_require_admin),
) -> dict:
    """
    更新提示词（仅基础提示词可编辑）

    更新基础提示词后，优化版本会自动失效，需要重新优化
    """
    db = next(get_db())
    try:
        prompt = db.query(SubagentPrompt).filter(SubagentPrompt.id == prompt_id).first()

        if not prompt:
            raise HTTPException(status_code=404, detail="提示词不存在")

        if prompt.prompt_type != "base":
            raise HTTPException(status_code=400, detail="只能编辑基础提示词（base 类型）")

        # 使用服务更新
        service = PromptManagementService()
        updated = service.update_base_prompt(
            subagent_name=prompt.subagent_name,
            new_content=request.content,
            notes=request.notes,
            user_id=user.id,
        )

        # 清除缓存，强制重新优化
        optimizer = get_prompt_optimizer()
        optimizer.clear_cache(prompt.subagent_name)

        return {
            "message": f"{prompt.subagent_name} 基础提示词已更新",
            "prompt_id": updated.id,
            "version": updated.version,
            "note": "优化版本已失效，下次 Agent 启动时会重新优化",
        }

    finally:
        db.close()


@router.post("/{prompt_id}/activate")
async def activate_prompt(
    prompt_id: int,
    user: User = Depends(_require_admin),
) -> dict:
    """激活指定版本的提示词"""
    service = PromptManagementService()
    activated = service.activate_prompt_version(prompt_id, user_id=user.id)

    # 清除缓存
    optimizer = get_prompt_optimizer()
    optimizer.clear_cache(activated.subagent_name)

    return {
        "message": f"{activated.subagent_name} 已激活版本 {activated.version}",
        "prompt_id": activated.id,
        "version": activated.version,
    }


@router.post("/initialize")
async def initialize_prompts(
    user: User = Depends(_require_admin),
) -> dict:
    """
    初始化基础提示词

    从静态文件导入基础提示词到数据库
    """
    service = PromptManagementService()
    created = service.initialize_base_prompts()

    return {
        "message": f"已初始化 {len(created)} 个基础提示词",
        "initialized": list(created.keys()),
    }


@router.post("/optimize/{subagent_name}")
async def trigger_optimization(
    subagent_name: str,
    user: User = Depends(_require_admin),
) -> dict:
    """
    手动触发 DSPy 优化

    清除缓存并重新优化提示词
    """
    valid_subagents = ["data-agent", "analyze-agent", "execute-agent"]
    if subagent_name not in valid_subagents:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid subagent_name: {subagent_name}. Valid options: {', '.join(valid_subagents)}"
        )

    # 清除缓存
    optimizer = get_prompt_optimizer()
    optimizer.clear_cache(subagent_name)

    # 触发优化
    try:
        from app.services.unified_prompt_optimizer import get_prompt_optimizer
        optimizer = get_prompt_optimizer()
        optimized_prompt = optimizer.get_prompt_for_agent(subagent_name)

        return {
            "message": f"{subagent_name} 提示词优化完成",
            "subagent_name": subagent_name,
            "prompt_length": len(optimized_prompt),
        }

    except Exception as e:
        logger.error(f"优化 {subagent_name} 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/current/{subagent_name}")
async def get_current_prompt(
    subagent_name: str,
    user: User = Depends(get_current_user),
) -> dict:
    """
    获取指定 Subagent 当前使用的提示词

    这是 Agent 实际使用的提示词（可能是优化后的）
    """
    try:
        from app.services.unified_prompt_optimizer import get_prompt_optimizer

        optimizer = get_prompt_optimizer()
        prompt_content = optimizer.get_prompt_for_agent(subagent_name)

        # 获取元数据
        db = next(get_db())
        try:
            active = (
                db.query(SubagentPrompt)
                .filter(
                    and_(
                        SubagentPrompt.subagent_name == subagent_name,
                        SubagentPrompt.is_active == True,
                    )
                )
                .first()
            )

            return {
                "subagent_name": subagent_name,
                "prompt_content": prompt_content,
                "version": active.version if active else "unknown",
                "type": active.prompt_type if active else "unknown",
                "is_optimized": active.prompt_type == "optimized" if active else False,
                "prompt_length": len(prompt_content),
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"获取 {subagent_name} 当前提示词失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
