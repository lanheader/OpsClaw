"""
提示词管理服务

负责提示词的 CRUD、DSPy 优化、版本管理
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from app.models.database import get_db
from app.models.subagent_prompt import SubagentPrompt, PromptChangeLog

logger = logging.getLogger(__name__)


class PromptManagementService:
    """提示词管理服务"""

    # 默认提示词映射
    DEFAULT_PROMPTS = {
        "data-agent": "app.prompts.subagents.data:DATA_AGENT_PROMPT",
        "analyze-agent": "app.prompts.subagents.analyze:ANALYZE_AGENT_PROMPT",
        "execute-agent": "app.prompts.subagents.execute:EXECUTE_AGENT_PROMPT",
    }

    @staticmethod
    def _import_static_prompt(subagent_name: str) -> str:
        """从静态文件导入默认提示词"""
        import importlib

        module_path, attr_name = PromptManagementService.DEFAULT_PROMPTS[subagent_name].rsplit(":", 1)
        module = importlib.import_module(module_path)
        return getattr(module, attr_name)

    def initialize_base_prompts(self) -> Dict[str, SubagentPrompt]:
        """
        初始化基础提示词到数据库

        Returns:
            创建的基础提示词字典
        """
        db = next(get_db())
        try:
            created = {}

            for subagent_name in ["data-agent", "analyze-agent", "execute-agent"]:
                # 检查是否已存在 base 版本
                existing = (
                    db.query(SubagentPrompt)
                    .filter(
                        and_(
                            SubagentPrompt.subagent_name == subagent_name,
                            SubagentPrompt.version == "base",
                            SubagentPrompt.prompt_type == "base",
                        )
                    )
                    .first()
                )

                if existing:
                    logger.info(f"{subagent_name} 的基础提示词已存在")
                    created[subagent_name] = existing
                    continue

                # 从静态文件导入
                prompt_content = self._import_static_prompt(subagent_name)

                # 创建基础提示词记录
                base_prompt = SubagentPrompt(
                    subagent_name=subagent_name,
                    version="base",
                    prompt_content=prompt_content,
                    prompt_type="base",
                    is_active=True,  # 基础版本默认激活
                    is_latest=True,
                    notes="从静态提示词文件导入的初始版本",
                )

                db.add(base_prompt)
                db.commit()
                db.refresh(base_prompt)

                # 记录变更日志
                self._log_change(
                    db=db,
                    subagent_name=subagent_name,
                    prompt_id=base_prompt.id,
                    change_type="create",
                    new_version="base",
                    new_content=prompt_content[:1000],
                    change_reason="初始化基础提示词",
                )

                created[subagent_name] = base_prompt
                logger.info(f"✅ {subagent_name} 基础提示词已初始化")

            return created

        finally:
            db.close()

    def get_active_prompt(self, subagent_name: str, db: Session) -> Optional[SubagentPrompt]:
        """
        获取激活的提示词

        Args:
            subagent_name: 子智能体名称
            db: 数据库会话

        Returns:
            激活的提示词，如果不存在则返回 None
        """
        return (
            db.query(SubagentPrompt)
            .filter(
                and_(
                    SubagentPrompt.subagent_name == subagent_name,
                    SubagentPrompt.is_active == True,
                )
            )
            .first()
        )

    def get_base_prompt(self, subagent_name: str, db: Session) -> Optional[SubagentPrompt]:
        """获取基础提示词"""
        return (
            db.query(SubagentPrompt)
            .filter(
                and_(
                    SubagentPrompt.subagent_name == subagent_name,
                    SubagentPrompt.version == "base",
                    SubagentPrompt.prompt_type == "base",
                )
            )
            .first()
        )

    def update_base_prompt(
        self,
        subagent_name: str,
        new_content: str,
        notes: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> SubagentPrompt:
        """
        更新基础提示词

        Args:
            subagent_name: 子智能体名称
            new_content: 新的提示词内容
            notes: 更新说明
            user_id: 操作用户 ID

        Returns:
            更新后的提示词
        """
        db = next(get_db())
        try:
            # 获取当前基础提示词
            base_prompt = self.get_base_prompt(subagent_name, db)
            if not base_prompt:
                raise ValueError(f"{subagent_name} 的基础提示词不存在")

            old_content = base_prompt.prompt_content

            # 更新内容
            base_prompt.prompt_content = new_content
            base_prompt.updated_by = user_id
            base_prompt.updated_at = datetime.utcnow()
            if notes:
                base_prompt.notes = notes

            db.commit()
            db.refresh(base_prompt)

            # 记录变更日志
            self._log_change(
                db=db,
                subagent_name=subagent_name,
                prompt_id=base_prompt.id,
                change_type="update",
                old_version="base",
                new_version="base",
                old_content=old_content[:1000],
                new_content=new_content[:1000],
                change_reason=notes or "用户手动更新",
                changed_by=user_id,
            )

            logger.info(f"✅ {subagent_name} 基础提示词已更新")
            return base_prompt

        finally:
            db.close()

    def list_all_prompts(self, subagent_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        列出所有提示词版本

        Args:
            subagent_name: 过滤子智能体名称

        Returns:
            提示词列表
        """
        db = next(get_db())
        try:
            query = db.query(SubagentPrompt)

            if subagent_name:
                query = query.filter(SubagentPrompt.subagent_name == subagent_name)

            prompts = query.order_by(
                SubagentPrompt.subagent_name,
                desc(SubagentPrompt.created_at)
            ).all()

            return [
                {
                    "id": p.id,
                    "subagent_name": p.subagent_name,
                    "version": p.version,
                    "prompt_type": p.prompt_type,
                    "is_active": p.is_active,
                    "is_latest": p.is_latest,
                    "performance_score": p.performance_score,
                    "usage_count": p.usage_count,
                    "notes": p.notes,
                    "created_at": p.created_at.isoformat(),
                    "updated_at": p.updated_at.isoformat(),
                    "content_preview": p.prompt_content[:200] + "..." if len(p.prompt_content) > 200 else p.prompt_content,
                }
                for p in prompts
            ]

        finally:
            db.close()

    def activate_prompt_version(self, prompt_id: int, user_id: Optional[int] = None) -> SubagentPrompt:
        """
        激活指定版本的提示词

        Args:
            prompt_id: 提示词 ID
            user_id: 操作用户 ID

        Returns:
            激活后的提示词
        """
        db = next(get_db())
        try:
            # 获取目标提示词
            target_prompt = db.query(SubagentPrompt).filter(SubagentPrompt.id == prompt_id).first()
            if not target_prompt:
                raise ValueError(f"提示词 ID {prompt_id} 不存在")

            subagent_name = target_prompt.subagent_name

            # 将同 subagent 的其他提示词设为非激活
            db.query(SubagentPrompt).filter(
                and_(
                    SubagentPrompt.subagent_name == subagent_name,
                    SubagentPrompt.id != prompt_id,
                )
            ).update({"is_active": False})

            # 激活目标提示词
            target_prompt.is_active = True

            db.commit()
            db.refresh(target_prompt)

            # 记录变更日志
            self._log_change(
                db=db,
                subagent_name=subagent_name,
                prompt_id=prompt_id,
                change_type="activate",
                new_version=target_prompt.version,
                new_content=target_prompt.prompt_content[:1000],
                change_reason=f"激活版本 {target_prompt.version}",
                changed_by=user_id,
            )

            logger.info(f"✅ {subagent_name} 已激活版本 {target_prompt.version}")
            return target_prompt

        finally:
            db.close()

    def _log_change(
        self,
        db: Session,
        subagent_name: str,
        prompt_id: Optional[int],
        change_type: str,
        new_version: str,
        new_content: Optional[str] = None,
        old_version: Optional[str] = None,
        old_content: Optional[str] = None,
        change_reason: Optional[str] = None,
        changed_by: Optional[int] = None,
        optimization_method: Optional[str] = None,
        training_examples_count: Optional[int] = None,
    ):
        """记录提示词变更日志"""
        log = PromptChangeLog(
            subagent_name=subagent_name,
            prompt_id=prompt_id,
            change_type=change_type,
            old_version=old_version,
            new_version=new_version,
            old_content=old_content,
            new_content=new_content,
            change_reason=change_reason,
            changed_by=changed_by,
            optimization_method=optimization_method,
            training_examples_count=training_examples_count,
        )
        db.add(log)


# ============== 全局便捷函数 ==============

def initialize_prompts() -> Dict[str, SubagentPrompt]:
    """初始化所有 Subagent 的基础提示词"""
    service = PromptManagementService()
    return service.initialize_base_prompts()


def get_prompt_for_agent(subagent_name: str) -> str:
    """
    为 Agent 获取提示词

    这是 Agent 使用时的主入口

    Args:
        subagent_name: 子智能体名称

    Returns:
        提示词内容
    """
    from app.services.unified_prompt_optimizer import get_prompt_optimizer

    # 使用统一优化器获取优化后的提示词
    optimizer = get_prompt_optimizer()
    return optimizer.get_prompt_for_agent(subagent_name)
