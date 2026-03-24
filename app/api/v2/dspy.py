"""
DSPy API 端点 - 提供 DSPy 状态查询和训练数据管理

注意：提示词优化功能已迁移到 unified_prompt_optimizer.py
"""

import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_

from app.dspy import is_dspy_available, is_configured, configure_dspy
from app.models.database import get_db
from app.models.subagent_prompt import SubagentPrompt
from app.models.dspy_prompt import TrainingExample, PromptOptimizationLog
from app.services.unified_prompt_optimizer import trigger_manual_optimization

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/dspy", tags=["DSPy"])


# ==================== Pydantic 模型 ====================

class StatsResponse(BaseModel):
    """统计信息响应"""
    dspy_available: bool = Field(description="DSPy 是否可用")
    configured: bool = Field(description="DSPy 是否已配置")
    total_examples: int = Field(description="训练示例总数")
    by_type: Dict[str, int] = Field(description="按类型统计")
    by_subagent: Dict[str, int] = Field(description="按 Subagent 统计")


# ==================== API 端点 ====================

@router.get("/health", summary="DSPy 健康检查")
async def health_check():
    """
    检查 DSPy 是否可用和已配置

    Returns:
        健康状态信息
    """
    return {
        "dspy_available": is_dspy_available(),
        "configured": is_configured(),
    }


@router.get("/stats", summary="获取统计信息")
async def get_stats() -> StatsResponse:
    """
    获取训练数据统计信息

    Returns:
        统计信息
    """
    db = next(get_db())
    try:
        # 训练示例总数
        total = db.query(TrainingExample).count()

        # 按类型统计
        by_type = {}
        for etype in ["query", "diagnose", "execute"]:
            count = (
                db.query(TrainingExample)
                .filter(TrainingExample.example_type == etype)
                .count()
            )
            by_type[etype] = count

        # 按 subagent 统计
        by_subagent = {}
        for name in ["data-agent", "analyze-agent", "execute-agent"]:
            count = (
                db.query(TrainingExample)
                .filter(TrainingExample.subagent_name == name)
                .count()
            )
            by_subagent[name] = count

        return StatsResponse(
            dspy_available=is_dspy_available(),
            configured=is_configured(),
            total_examples=total,
            by_type=by_type,
            by_subagent=by_subagent,
        )

    finally:
        db.close()


@router.get("/training/examples", summary="获取训练示例列表")
async def get_training_examples(
    subagent_name: Optional[str] = Query(None, description="过滤 Subagent"),
    example_type: Optional[str] = Query(None, description="过滤类型"),
    unused_only: bool = Query(False, description="只显示未使用的示例"),
    limit: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """
    获取训练示例列表

    Args:
        subagent_name: Subagent 过滤
        example_type: 类型过滤
        unused_only: 只显示未使用的
        limit: 限制数量

    Returns:
        训练示例列表
    """
    try:
        db = next(get_db())
        try:
            query = db.query(TrainingExample)

            # 应用过滤器
            if subagent_name:
                query = query.filter(TrainingExample.subagent_name == subagent_name)
            if example_type:
                query = query.filter(TrainingExample.example_type == example_type)
            if unused_only:
                query = query.filter(TrainingExample.is_used_for_optimization == False)

            # 排序和限制
            from sqlalchemy import desc
            examples = (
                query.order_by(desc(TrainingExample.created_at))
                .limit(limit)
                .all()
            )

            return {
                "total": len(examples),
                "examples": [
                    {
                        "id": ex.id,
                        "subagent_name": ex.subagent_name,
                        "example_type": ex.example_type,
                        "user_input": ex.user_input[:200] + "..." if len(ex.user_input) > 200 else ex.user_input,
                        "agent_output": ex.agent_output[:200] + "..." if len(ex.agent_output) > 200 else ex.agent_output,
                        "quality_score": ex.quality_score,
                        "is_used_for_optimization": ex.is_used_for_optimization,
                        "used_in_prompt_version": ex.used_in_prompt_version,
                        "created_at": ex.created_at.isoformat(),
                    }
                    for ex in examples
                ],
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"获取训练示例时出错: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/subagents/status", summary="获取所有 Subagents 的 DSPy 优化状态")
async def get_subagents_status() -> Dict[str, Any]:
    """
    获取所有 Subagents 的 DSPy 优化状态

    Returns:
        各 Subagent 的优化状态信息
    """
    try:
        valid_subagents = ["data-agent", "analyze-agent", "execute-agent"]
        status = {}

        db = next(get_db())
        try:
            for subagent_name in valid_subagents:
                # 检查数据库中是否有优化版本（使用 SubagentPrompt 表）
                latest_prompt = (
                    db.query(SubagentPrompt)
                    .filter(
                        and_(
                            SubagentPrompt.subagent_name == subagent_name,
                            SubagentPrompt.prompt_type == "optimized",
                            SubagentPrompt.is_latest == True,
                            SubagentPrompt.is_active == True,
                        )
                    )
                    .first()
                )

                # 检查训练示例数量
                unused_examples = (
                    db.query(TrainingExample)
                    .filter(
                        and_(
                            TrainingExample.subagent_name == subagent_name,
                            TrainingExample.is_used_for_optimization == False,
                            TrainingExample.quality_score >= 0.6,
                        )
                    )
                    .count()
                )

                status[subagent_name] = {
                    "subagent_name": subagent_name,
                    "dspy_available": is_dspy_available(),
                    "using_optimized": latest_prompt is not None,
                    "optimized_version": latest_prompt.version if latest_prompt else None,
                    "optimized_at": latest_prompt.created_at.isoformat() if latest_prompt else None,
                    "usage_count": latest_prompt.usage_count if latest_prompt else 0,
                    "performance_score": latest_prompt.performance_score if latest_prompt else 0,
                    "few_shot_count": len(latest_prompt.few_shot_examples or []) if latest_prompt else 0,
                    "unused_examples_for_optimization": unused_examples,
                    "auto_optimize_ready": unused_examples >= 5,  # 是否可以触发自动优化
                }
        finally:
            db.close()

        return {
            "dspy_available": is_dspy_available(),
            "configured": is_configured(),
            "subagents": status,
        }

    except Exception as e:
        logger.error(f"获取 Subagent 状态时出错: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimize/{subagent_name}", summary="触发提示词优化")
async def trigger_optimization(
    subagent_name: str,
) -> Dict[str, Any]:
    """
    手动触发指定 Subagent 的提示词优化

    Args:
        subagent_name: 子智能体名称

    Returns:
        优化结果
    """
    # 验证子智能体名称
    valid_subagents = ["data-agent", "analyze-agent", "execute-agent"]
    if subagent_name not in valid_subagents:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid subagent_name: {subagent_name}. Valid options: {', '.join(valid_subagents)}"
        )

    try:
        log = await trigger_manual_optimization(subagent_name)

        return {
            "subagent_name": subagent_name,
            "status": log.status,
            "version": log.new_version,
            "training_examples_count": log.training_examples_count,
            "duration_seconds": log.duration_seconds,
            "started_at": log.started_at.isoformat(),
            "completed_at": log.completed_at.isoformat() if log.completed_at else None,
        }

    except Exception as e:
        logger.error(f"触发优化时出错: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/optimization/logs", summary="获取优化日志")
async def get_optimization_logs(
    subagent_name: Optional[str] = Query(None, description="过滤 Subagent"),
    limit: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    """
    获取提示词优化日志

    Args:
        subagent_name: Subagent 过滤
        limit: 限制数量

    Returns:
        优化日志列表
    """
    try:
        db = next(get_db())
        try:
            query = db.query(PromptOptimizationLog)

            if subagent_name:
                query = query.filter(PromptOptimizationLog.subagent_name == subagent_name)

            from sqlalchemy import desc
            logs = (
                query.order_by(desc(PromptOptimizationLog.started_at))
                .limit(limit)
                .all()
            )

            return {
                "total": len(logs),
                "logs": [
                    {
                        "id": log.id,
                        "subagent_name": log.subagent_name,
                        "status": log.status,
                        "new_version": log.new_version,
                        "training_examples_count": log.training_examples_count,
                        "trigger_type": log.trigger_type,
                        "optimization_method": log.optimization_method,
                        "duration_seconds": log.duration_seconds,
                        "started_at": log.started_at.isoformat(),
                        "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                        "error_message": log.error_message,
                    }
                    for log in logs
                ],
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"获取优化日志时出错: {e}")
        raise HTTPException(status_code=500, detail=str(e))
