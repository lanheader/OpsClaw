"""知识库域模型"""

from app.models.database import get_knowledge_db, session_makers, engines, bases
from app.models.knowledge.incident import IncidentKnowledgeBase
from app.models.knowledge.agent_prompt import AgentPrompt, PromptVersion

# 域级数据库访问
get_db = get_knowledge_db
engine = engines["knowledge"]
SessionLocal = session_makers["knowledge"]
Base = bases["knowledge"]

__all__ = [
    "IncidentKnowledgeBase",
    "AgentPrompt",
    "PromptVersion",
    "get_db",
    "engine",
    "SessionLocal",
    "Base",
]
