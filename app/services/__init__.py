"""Service layer for business logic

服务层模块，包含所有业务逻辑服务。

模块分类：
- 飞书集成：approval_intent_service, chat_service, session_state_manager
- 批准流程：approval_config_service
- 提示词管理：prompt_management, unified_prompt_optimizer
"""

# 飞书相关服务
from app.services.approval_intent_service import (
    classify_approval_intent,
    is_approval_keyword,
    is_rejection_keyword,
)
from app.services.chat_service import (
    get_or_create_feishu_session,
    save_feishu_message,
)
from app.services.session_state_manager import SessionStateManager

# 批准配置服务（按需导入）
# from app.services.approval_config_service import ApprovalConfigService

# 提示词管理服务（按需导入）
# from app.services.prompt_management import PromptManagementService
# from app.services.unified_prompt_optimizer import UnifiedPromptOptimizer

__all__ = [
    # 飞书集成
    "classify_approval_intent",
    "is_approval_keyword",
    "is_rejection_keyword",
    "get_or_create_feishu_session",
    "save_feishu_message",
    "SessionStateManager",
]
