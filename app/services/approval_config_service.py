"""审批配置服务 - 管理哪些工具需要审批"""

import logging
from typing import List, Dict, Any, Optional, Set

from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.models.approval_config import ApprovalConfig
from app.tools.registry import ToolRegistry
from app.tools.base import RiskLevel

logger = logging.getLogger(__name__)


class ApprovalConfigService:
    """审批配置服务"""

    @staticmethod
    def sync_tools_to_db(db: Session) -> int:
        """
        将 ToolRegistry 中的工具同步到 approval_configs 表

        Returns:
            同步的工具数量
        """
        registry = ToolRegistry()
        tool_classes = registry.list_tools()

        synced_count = 0
        for tool_class in tool_classes:
            metadata = tool_class.get_metadata()
            if not metadata:
                continue

            tool_name = metadata.name
            tool_group = metadata.group or "default"
            risk_level = metadata.risk_level.value if metadata.risk_level else "unknown"
            description = metadata.description or ""
            permissions = metadata.permissions or []

            # 默认：HIGH 风险需要审批，其他不需要
            requires_approval = metadata.risk_level == RiskLevel.HIGH

            # 查找现有记录
            existing = (
                db.query(ApprovalConfig)
                .filter(ApprovalConfig.tool_name == tool_name)
                .first()
            )

            if existing:
                # 更新现有记录（保留 requires_approval 的手动配置）
                existing.tool_group = tool_group
                existing.risk_level = risk_level
                existing.description = description
                # 如果是新同步的工具，才设置默认值
                if existing.approval_roles is None:
                    existing.approval_roles = []
                if existing.exempt_roles is None:
                    existing.exempt_roles = []
            else:
                # 创建新记录
                new_config = ApprovalConfig(
                    tool_name=tool_name,
                    tool_group=tool_group,
                    risk_level=risk_level,
                    requires_approval=requires_approval,
                    approval_roles=[],
                    exempt_roles=[],
                    description=description,
                )
                db.add(new_config)
                synced_count += 1

        db.commit()
        logger.info(f"同步工具到审批配置表: 新增 {synced_count} 个工具")
        return synced_count

    @staticmethod
    def get_tools_require_approval(
        db: Session, user_role: Optional[str] = None
    ) -> Set[str]:
        """
        获取需要审批的工具列表（考虑角色豁免）

        Args:
            db: 数据库会话
            user_role: 用户角色（用于角色豁免检查）

        Returns:
            需要审批的工具名称集合
        """
        query = db.query(ApprovalConfig).filter(
            ApprovalConfig.requires_approval == True
        )

        tools_to_approve = set()
        for config in query.all():
            # 检查角色豁免
            if user_role and config.exempt_roles:
                if user_role in config.exempt_roles:
                    continue

            # 检查角色限制（如果配置了 approval_roles，只有这些角色需要审批）
            if user_role and config.approval_roles:
                if user_role not in config.approval_roles:
                    continue

            tools_to_approve.add(config.tool_name)

        return tools_to_approve

    @staticmethod
    def set_tool_approval_enabled(
        db: Session, tool_name: str, requires_approval: bool
    ) -> bool:
        """
        设置工具是否需要审批

        Args:
            db: 数据库会话
            tool_name: 工具名称
            requires_approval: 是否需要审批

        Returns:
            是否设置成功
        """
        config = (
            db.query(ApprovalConfig)
            .filter(ApprovalConfig.tool_name == tool_name)
            .first()
        )

        if not config:
            logger.warning(f"工具不存在: {tool_name}")
            return False

        config.requires_approval = requires_approval
        db.commit()
        logger.info(f"更新工具审批状态: {tool_name} -> requires_approval={requires_approval}")
        return True

    @staticmethod
    def get_approval_config(
        db: Session,
        group_code: Optional[str] = None,
        risk_level: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取审批配置列表（供 Web 界面使用）

        Args:
            db: 数据库会话
            group_code: 工具分组筛选（可选）
            risk_level: 风险等级筛选（可选）

        Returns:
            审批配置列表
        """
        query = db.query(ApprovalConfig)

        if group_code:
            query = query.filter(ApprovalConfig.tool_group == group_code)

        if risk_level:
            query = query.filter(ApprovalConfig.risk_level == risk_level)

        configs = query.order_by(ApprovalConfig.tool_group, ApprovalConfig.tool_name).all()
        return [config.to_dict() for config in configs]

    @staticmethod
    def get_approval_groups(db: Session) -> List[str]:
        """获取所有工具分组"""
        groups = (
            db.query(ApprovalConfig.tool_group)
            .distinct()
            .order_by(ApprovalConfig.tool_group)
            .all()
        )
        return [g[0] for g in groups if g[0]]

    @staticmethod
    def batch_update_approval(
        db: Session, tool_names: List[str], requires_approval: bool
    ) -> int:
        """
        批量更新工具审批状态

        Args:
            db: 数据库会话
            tool_names: 工具名称列表
            requires_approval: 是否需要审批

        Returns:
            更新的工具数量
        """
        updated = (
            db.query(ApprovalConfig)
            .filter(ApprovalConfig.tool_name.in_(tool_names))
            .update({"requires_approval": requires_approval}, synchronize_session=False)
        )
        db.commit()
        logger.info(
            f"批量更新审批状态: {updated} 个工具 -> requires_approval={requires_approval}"
        )
        return updated

    @staticmethod
    def get_tool_config(db: Session, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        获取单个工具的审批配置

        Args:
            db: 数据库会话
            tool_name: 工具名称

        Returns:
            工具配置字典，如果不存在则返回 None
        """
        config = (
            db.query(ApprovalConfig)
            .filter(ApprovalConfig.tool_name == tool_name)
            .first()
        )
        return config.to_dict() if config else None
