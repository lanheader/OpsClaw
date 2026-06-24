# app/models/__init__.py
"""Database models for ops-agent-langgraph

按功能域组织的数据库模型：
- auth: 认证授权域
- chat: 聊天会话域
- workflow: 工作流域
- knowledge: 知识库域
- config: 配置域
"""

from app.models.database import Base, get_db

# 认证授权域
from app.models.auth import (
    User,
    Role,
    Permission,
    UserRole,
    RolePermission,
    LoginHistory,
)

# 聊天会话域
from app.models.chat import (
    ChatSession,
    SessionState,
    ChatMessage,
    MessageRole,
)

# 工作流域
from app.models.workflow import (
    WorkflowExecution,
    ScheduledTask,
    TaskType,
    TaskExecution,
    ExecutionStatus,
)

# 知识库域
from app.models.knowledge import (
    IncidentKnowledgeBase,
    AgentPrompt,
    PromptVersion,
)

# 配置域
from app.models.config import (
    ApprovalConfig,
    SystemSetting,
)

__all__ = [
    # 数据库基础
    "Base",
    "get_db",
    # 认证授权域
    "User",
    "Role",
    "Permission",
    "UserRole",
    "RolePermission",
    "LoginHistory",
    # 聊天会话域
    "ChatSession",
    "SessionState",
    "ChatMessage",
    "MessageRole",
    # 工作流域
    "WorkflowExecution",
    "ScheduledTask",
    "TaskType",
    "TaskExecution",
    "ExecutionStatus",
    # 知识库域
    "IncidentKnowledgeBase",
    "AgentPrompt",
    "PromptVersion",
    # 配置域
    "ApprovalConfig",
    "SystemSetting",
]
