"""
运维知识库 API 端点

提供历史故障案例的 CRUD 操作和检索功能
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_

from app.models.database import get_db
from app.models.user import User
from app.core.deps import get_current_user
from app.models.incident_knowledge import IncidentKnowledgeBase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])


# ==================== Pydantic 模型 ====================

class IncidentCreate(BaseModel):
    """创建事故知识库条目"""
    issue_title: str = Field(..., description="问题标题")
    issue_description: str = Field(..., description="问题描述")
    symptoms: str = Field(None, description="症状描述")  # type: ignore[assignment]
    root_cause: str = Field(None, description="根本原因")  # type: ignore[assignment]
    solution: str = Field(None, description="解决方案")  # type: ignore[assignment]
    effectiveness_score: float = Field(0.5, ge=0, le=1, description="有效性评分 (0-1)")
    severity: str = Field("medium", description="严重程度")
    affected_system: str = Field(None, description="受影响系统")  # type: ignore[assignment]
    category: str = Field(None, description="分类")  # type: ignore[assignment]
    tags: str = Field(None, description="标签，逗号分隔")  # type: ignore[assignment]


class IncidentUpdate(BaseModel):
    """更新事故知识库条目"""
    issue_title: str = Field(None, description="问题标题")  # type: ignore[assignment]
    issue_description: str = Field(None, description="问题描述")  # type: ignore[assignment]
    symptoms: str = Field(None, description="症状描述")  # type: ignore[assignment]
    root_cause: str = Field(None, description="根本原因")  # type: ignore[assignment]
    solution: str = Field(None, description="解决方案")  # type: ignore[assignment]
    effectiveness_score: float = Field(None, ge=0, le=1, description="有效性评分")  # type: ignore[assignment]
    severity: str = Field(None, description="严重程度")  # type: ignore[assignment]
    affected_system: str = Field(None, description="受影响系统")  # type: ignore[assignment]
    category: str = Field(None, description="分类")  # type: ignore[assignment]
    tags: str = Field(None, description="标签，逗号分隔")  # type: ignore[assignment]
    is_verified: bool = Field(None, description="是否已验证")  # type: ignore[assignment]


class IncidentResponse(BaseModel):
    """事故知识库响应"""
    id: int
    issue_title: str
    issue_description: str
    symptoms: Optional[str]
    root_cause: Optional[str]
    solution: Optional[str]
    effectiveness_score: float
    severity: Optional[str]
    affected_system: Optional[str]
    category: Optional[str]
    tags: Optional[str]
    is_verified: bool
    is_active: bool
    created_at: str
    updated_at: str


# ==================== 辅助函数 ====================

def _require_admin(user: User = Depends(get_current_user)):  # type: ignore[no-untyped-def]
    """要求管理员权限"""
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="需要管理员权限")


# ==================== API 端点 ====================

@router.get("/search", response_model=List[IncidentResponse])
async def search_incidents(
    query: str = Query(..., description="搜索关键词"),
    category: Optional[str] = Query(None, description="分类过滤"),
    severity: Optional[str] = Query(None, description="严重程度过滤"),
    limit: int = Query(10, ge=1, le=50, description="返回数量"),
    user: User = Depends(get_current_user),
) -> List[IncidentResponse]:
    """
    搜索事故知识库

    支持按标题、描述、症状、根因、解决方案搜索
    """
    db = next(get_db())
    try:
        # 构建查询
        query_filter = or_(
            IncidentKnowledgeBase.issue_title.like(f"%{query}%"),
            IncidentKnowledgeBase.issue_description.like(f"%{query}%"),
            IncidentKnowledgeBase.symptoms.like(f"%{query}%"),
            IncidentKnowledgeBase.root_cause.like(f"%{query}%"),
            IncidentKnowledgeBase.solution.like(f"%{query}%"),
        )

        db_query = db.query(IncidentKnowledgeBase).filter(query_filter)

        # 添加过滤条件
        if category:
            db_query = db_query.filter(IncidentKnowledgeBase.category == category)
        if severity:
            db_query = db_query.filter(IncidentKnowledgeBase.severity == severity)

        # 只返回有效的记录
        db_query = db_query.filter(IncidentKnowledgeBase.is_active == True)

        # 排序和限制
        incidents = (
            db_query
            .order_by(IncidentKnowledgeBase.effectiveness_score.desc())
            .order_by(IncidentKnowledgeBase.created_at.desc())
            .limit(limit)
            .all()
        )

        return [
            IncidentResponse(
                id=inc.id,  # type: ignore[arg-type]
                issue_title=inc.issue_title,  # type: ignore[arg-type]
                issue_description=inc.issue_description,  # type: ignore[arg-type]
                symptoms=inc.symptoms,  # type: ignore[arg-type]
                root_cause=inc.root_cause,  # type: ignore[arg-type]
                solution=inc.solution,  # type: ignore[arg-type]
                effectiveness_score=inc.effectiveness_score,  # type: ignore[arg-type]
                severity=inc.severity,  # type: ignore[arg-type]
                affected_system=inc.affected_system,  # type: ignore[arg-type]
                category=inc.category,  # type: ignore[arg-type]
                tags=inc.tags,  # type: ignore[arg-type]
                is_verified=inc.is_verified,  # type: ignore[arg-type]
                is_active=inc.is_active,  # type: ignore[arg-type]
                created_at=inc.created_at.isoformat(),
                updated_at=inc.updated_at.isoformat(),
            )
            for inc in incidents
        ]

    finally:
        db.close()


@router.get("/list", response_model=List[IncidentResponse])
async def list_incidents(
    category: Optional[str] = Query(None, description="分类过滤"),
    severity: Optional[str] = Query(None, description="严重程度过滤"),
    is_verified: Optional[bool] = Query(None, description="是否已验证"),
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    user: User = Depends(get_current_user),
) -> List[IncidentResponse]:
    """列出事故知识库条目"""
    db = next(get_db())
    try:
        db_query = db.query(IncidentKnowledgeBase)

        # 添加过滤条件
        if category:
            db_query = db_query.filter(IncidentKnowledgeBase.category == category)
        if severity:
            db_query = db_query.filter(IncidentKnowledgeBase.severity == severity)
        if is_verified is not None:
            db_query = db_query.filter(IncidentKnowledgeBase.is_verified == is_verified)

        # 只返回有效的记录
        db_query = db_query.filter(IncidentKnowledgeBase.is_active == True)

        # 排序和分页
        incidents = (
            db_query
            .order_by(IncidentKnowledgeBase.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [
            IncidentResponse(
                id=inc.id,  # type: ignore[arg-type]
                issue_title=inc.issue_title,  # type: ignore[arg-type]
                issue_description=inc.issue_description,  # type: ignore[arg-type]
                symptoms=inc.symptoms,  # type: ignore[arg-type]
                root_cause=inc.root_cause,  # type: ignore[arg-type]
                solution=inc.solution,  # type: ignore[arg-type]
                effectiveness_score=inc.effectiveness_score,  # type: ignore[arg-type]
                severity=inc.severity,  # type: ignore[arg-type]
                affected_system=inc.affected_system,  # type: ignore[arg-type]
                category=inc.category,  # type: ignore[arg-type]
                tags=inc.tags,  # type: ignore[arg-type]
                is_verified=inc.is_verified,  # type: ignore[arg-type]
                is_active=inc.is_active,  # type: ignore[arg-type]
                created_at=inc.created_at.isoformat(),
                updated_at=inc.updated_at.isoformat(),
            )
            for inc in incidents
        ]

    finally:
        db.close()


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: int,
    user: User = Depends(get_current_user),
) -> IncidentResponse:
    """获取单个事故知识库条目"""
    db = next(get_db())
    try:
        incident = db.query(IncidentKnowledgeBase).filter(
            IncidentKnowledgeBase.id == incident_id
        ).first()

        if not incident:
            raise HTTPException(status_code=404, detail="知识库条目不存在")

        return IncidentResponse(
            id=incident.id,  # type: ignore[arg-type]
            issue_title=incident.issue_title,  # type: ignore[arg-type]
            issue_description=incident.issue_description,  # type: ignore[arg-type]
            symptoms=incident.symptoms,  # type: ignore[arg-type]
            root_cause=incident.root_cause,  # type: ignore[arg-type]
            solution=incident.solution,  # type: ignore[arg-type]
            effectiveness_score=incident.effectiveness_score,  # type: ignore[arg-type]
            severity=incident.severity,  # type: ignore[arg-type]
            affected_system=incident.affected_system,  # type: ignore[arg-type]
            category=incident.category,  # type: ignore[arg-type]
            tags=incident.tags,  # type: ignore[arg-type]
            is_verified=incident.is_verified,  # type: ignore[arg-type]
            is_active=incident.is_active,  # type: ignore[arg-type]
            created_at=incident.created_at.isoformat(),
            updated_at=incident.updated_at.isoformat(),
        )

    finally:
        db.close()


@router.post("", response_model=IncidentResponse)
async def create_incident(
    data: IncidentCreate,
    user: User = Depends(_require_admin),
) -> IncidentResponse:
    """创建事故知识库条目"""
    db = next(get_db())
    try:
        incident = IncidentKnowledgeBase(
            issue_title=data.issue_title,
            issue_description=data.issue_description,
            symptoms=data.symptoms,
            root_cause=data.root_cause,
            solution=data.solution,
            effectiveness_score=data.effectiveness_score,
            severity=data.severity,
            affected_system=data.affected_system,
            category=data.category,
            tags=data.tags,
        )

        db.add(incident)
        db.commit()
        db.refresh(incident)

        logger.info(f"创建知识库条目: {incident.id} - {incident.issue_title}")

        return IncidentResponse(
            id=incident.id,  # type: ignore[arg-type]
            issue_title=incident.issue_title,  # type: ignore[arg-type]
            issue_description=incident.issue_description,  # type: ignore[arg-type]
            symptoms=incident.symptoms,  # type: ignore[arg-type]
            root_cause=incident.root_cause,  # type: ignore[arg-type]
            solution=incident.solution,  # type: ignore[arg-type]
            effectiveness_score=incident.effectiveness_score,  # type: ignore[arg-type]
            severity=incident.severity,  # type: ignore[arg-type]
            affected_system=incident.affected_system,  # type: ignore[arg-type]
            category=incident.category,  # type: ignore[arg-type]
            tags=incident.tags,  # type: ignore[arg-type]
            is_verified=incident.is_verified,  # type: ignore[arg-type]
            is_active=incident.is_active,  # type: ignore[arg-type]
            created_at=incident.created_at.isoformat(),
            updated_at=incident.updated_at.isoformat(),
        )

    finally:
        db.close()


@router.put("/{incident_id}", response_model=IncidentResponse)
async def update_incident(
    incident_id: int,
    data: IncidentUpdate,
    user: User = Depends(_require_admin),
) -> IncidentResponse:
    """更新事故知识库条目"""
    db = next(get_db())
    try:
        incident = db.query(IncidentKnowledgeBase).filter(
            IncidentKnowledgeBase.id == incident_id
        ).first()

        if not incident:
            raise HTTPException(status_code=404, detail="知识库条目不存在")

        # 更新字段
        if data.issue_title is not None:
            incident.issue_title = data.issue_title  # type: ignore[assignment]
        if data.issue_description is not None:
            incident.issue_description = data.issue_description  # type: ignore[assignment]
        if data.symptoms is not None:
            incident.symptoms = data.symptoms  # type: ignore[assignment]
        if data.root_cause is not None:
            incident.root_cause = data.root_cause  # type: ignore[assignment]
        if data.solution is not None:
            incident.solution = data.solution  # type: ignore[assignment]
        if data.effectiveness_score is not None:
            incident.effectiveness_score = data.effectiveness_score  # type: ignore[assignment]
        if data.severity is not None:
            incident.severity = data.severity  # type: ignore[assignment]
        if data.affected_system is not None:
            incident.affected_system = data.affected_system  # type: ignore[assignment]
        if data.category is not None:
            incident.category = data.category  # type: ignore[assignment]
        if data.tags is not None:
            incident.tags = data.tags  # type: ignore[assignment]
        if data.is_verified is not None:
            incident.is_verified = data.is_verified  # type: ignore[assignment]

        db.commit()
        db.refresh(incident)

        logger.info(f"更新知识库条目: {incident.id}")

        return IncidentResponse(
            id=incident.id,  # type: ignore[arg-type]
            issue_title=incident.issue_title,  # type: ignore[arg-type]
            issue_description=incident.issue_description,  # type: ignore[arg-type]
            symptoms=incident.symptoms,  # type: ignore[arg-type]
            root_cause=incident.root_cause,  # type: ignore[arg-type]
            solution=incident.solution,  # type: ignore[arg-type]
            effectiveness_score=incident.effectiveness_score,  # type: ignore[arg-type]
            severity=incident.severity,  # type: ignore[arg-type]
            affected_system=incident.affected_system,  # type: ignore[arg-type]
            category=incident.category,  # type: ignore[arg-type]
            tags=incident.tags,  # type: ignore[arg-type]
            is_verified=incident.is_verified,  # type: ignore[arg-type]
            is_active=incident.is_active,  # type: ignore[arg-type]
            created_at=incident.created_at.isoformat(),
            updated_at=incident.updated_at.isoformat(),
        )

    finally:
        db.close()


@router.delete("/{incident_id}")
async def delete_incident(
    incident_id: int,
    user: User = Depends(_require_admin),
) -> dict:
    """删除事故知识库条目（软删除）"""
    db = next(get_db())
    try:
        incident = db.query(IncidentKnowledgeBase).filter(
            IncidentKnowledgeBase.id == incident_id
        ).first()

        if not incident:
            raise HTTPException(status_code=404, detail="知识库条目不存在")

        # 软删除
        incident.is_active = False  # type: ignore[assignment]
        db.commit()

        logger.info(f"删除知识库条目: {incident_id}")

        return {"message": "知识库条目已删除", "id": incident_id}

    finally:
        db.close()


@router.get("/stats/summary")
async def get_knowledge_stats(
    user: User = Depends(get_current_user),
) -> dict:
    """获取知识库统计信息"""
    db = next(get_db())
    try:
        total = db.query(IncidentKnowledgeBase).filter(
            IncidentKnowledgeBase.is_active == True
        ).count()

        verified = db.query(IncidentKnowledgeBase).filter(
            and_(
                IncidentKnowledgeBase.is_active == True,
                IncidentKnowledgeBase.is_verified == True
            )
        ).count()

        # 按分类统计
        category_stats = {}
        for category in ["network", "storage", "application", "database", "kubernetes", "other"]:
            count = db.query(IncidentKnowledgeBase).filter(
                and_(
                    IncidentKnowledgeBase.is_active == True,
                    IncidentKnowledgeBase.category == category
                )
            ).count()
            if count > 0:
                category_stats[category] = count

        # 按严重程度统计
        severity_stats = {}
        for severity in ["low", "medium", "high", "critical"]:
            count = db.query(IncidentKnowledgeBase).filter(
                and_(
                    IncidentKnowledgeBase.is_active == True,
                    IncidentKnowledgeBase.severity == severity
                )
            ).count()
            if count > 0:
                severity_stats[severity] = count

        return {
            "total_incidents": total,
            "verified_incidents": verified,
            "by_category": category_stats,
            "by_severity": severity_stats,
        }

    finally:
        db.close()
