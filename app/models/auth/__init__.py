"""认证授权域模型"""

from app.models.database import get_auth_db, session_makers, engines, bases
from app.models.auth.user import User
from app.models.auth.role import Role
from app.models.auth.permission import Permission
from app.models.auth.user_role import UserRole
from app.models.auth.role_permission import RolePermission
from app.models.auth.login_history import LoginHistory

# 域级数据库访问
get_db = get_auth_db
engine = engines["auth"]
SessionLocal = session_makers["auth"]
Base = bases["auth"]

__all__ = [
    "User",
    "Role",
    "Permission",
    "UserRole",
    "RolePermission",
    "LoginHistory",
    "get_db",
    "engine",
    "SessionLocal",
    "Base",
]
