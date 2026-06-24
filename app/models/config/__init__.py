"""配置域模型"""

from app.models.database import get_config_db, session_makers, engines, bases
from app.models.config.approval import ApprovalConfig
from app.models.config.system_setting import SystemSetting

# 域级数据库访问
get_db = get_config_db
engine = engines["config"]
SessionLocal = session_makers["config"]
Base = bases["config"]

__all__ = [
    "ApprovalConfig",
    "SystemSetting",
    "get_db",
    "engine",
    "SessionLocal",
    "Base",
]
