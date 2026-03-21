"""
命令执行工具（从 command_executor_tools.py 迁移）

所有工具都需要 command.execute 权限才能使用。
"""

import logging
from typing import Dict, Any, Optional
from langchain_core.tools import tool
from sqlalchemy.orm import Session

from app.core.permission_checker import check_tool_permission

logger = logging.getLogger(__name__)


@tool
async def execute_kubectl_command_tool(
    command: str,
    user_id: int,
    db: Session,
    namespace: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    执行 kubectl 命令（只允许读操作）

    需要权限: command.execute

    Args:
        command: kubectl 子命令
        user_id: 用户ID（用于权限检查）
        db: 数据库会话（用于权限检查）
        namespace: 可选的命名空间
        timeout: 命令超时时间
    """
    # 权限检查
    check_tool_permission(db, user_id, "command.execute", raise_exception=True)

    from app.tools.command_executor_tools import execute_kubectl_command
    return await execute_kubectl_command.ainvoke({"command": command, "namespace": namespace, "timeout": timeout})


@tool
async def execute_redis_command_tool(
    command: str,
    user_id: int,
    db: Session,
    host: str = "localhost",
    port: int = 6379,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    执行 redis-cli 命令（只允许读操作）

    需要权限: command.execute

    Args:
        command: Redis 命令
        user_id: 用户ID（用于权限检查）
        db: 数据库会话（用于权限检查）
        host: Redis 主机地址
        port: Redis 端口
        timeout: 命令超时时间
    """
    # 权限检查
    check_tool_permission(db, user_id, "command.execute", raise_exception=True)

    from app.tools.command_executor_tools import execute_redis_command
    return await execute_redis_command.ainvoke({"command": command, "host": host, "port": port, "timeout": timeout})


@tool
async def execute_mysql_query_tool(
    query: str,
    user_id: int,
    db: Session,
    database: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    执行 MySQL 查询（只允许 SELECT/SHOW）

    需要权限: command.execute

    Args:
        query: SQL 查询语句
        user_id: 用户ID（用于权限检查）
        db: 数据库会话（用于权限检查）
        database: 可选的数据库名
        timeout: 查询超时时间
    """
    # 权限检查
    check_tool_permission(db, user_id, "command.execute", raise_exception=True)

    from app.tools.command_executor_tools import execute_mysql_query
    return await execute_mysql_query.ainvoke({"query": query, "database": database, "timeout": timeout})


@tool
async def execute_safe_shell_command_tool(
    command: str,
    user_id: int,
    db: Session,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    执行安全的 shell 命令（白名单机制）

    需要权限: command.execute

    Args:
        command: shell 命令
        user_id: 用户ID（用于权限检查）
        db: 数据库会话（用于权限检查）
        timeout: 命令超时时间
    """
    # 权限检查
    check_tool_permission(db, user_id, "command.execute", raise_exception=True)

    from app.tools.command_executor_tools import execute_safe_shell_command
    return await execute_safe_shell_command.ainvoke({"command": command, "timeout": timeout})


__all__ = [
    "execute_kubectl_command_tool",
    "execute_redis_command_tool",
    "execute_mysql_query_tool",
    "execute_safe_shell_command_tool",
]
