"""
命令执行客户端包装器

提供统一的命令执行接口，支持：
- 命令超时控制
- 环境变量继承
- 输出捕获
- 错误处理
"""

import asyncio
import logging
import os
import re
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from app.core.permission_checker import check_tool_permission

logger = logging.getLogger(__name__)


class CommandExecutionError(Exception):
    """命令执行错误"""
    def __init__(self, command: str, exit_code: int, error: str):
        self.command = command
        self.exit_code = exit_code
        self.error = error
        super().__init__(f"Command '{command}' failed with exit code {exit_code}: {error}")


class CommandTimeoutError(Exception):
    """命令超时错误"""
    def __init__(self, command: str, timeout: int):
        self.command = command
        self.timeout = timeout
        super().__init__(f"Command '{command}' timed out after {timeout} seconds")


class CommandExecutor:
    """
    命令执行器

    提供统一的命令执行接口，支持权限检查和超时控制。
    """

    def __init__(self, default_timeout: int = 30):
        """
        初始化命令执行器

        Args:
            default_timeout: 默认超时时间（秒）
        """
        self.default_timeout = default_timeout
        self.command_history: List[Dict[str, Any]] = []

    async def execute(
        self,
        command: str,
        user_id: int,
        db: Session,
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
        check_permission: bool = True,
        permission: str = "command.execute",
    ) -> Dict[str, Any]:
        """
        执行命令

        Args:
            command: 要执行的命令
            user_id: 用户ID（用于权限检查）
            db: 数据库会话（用于权限检查）
            timeout: 超时时间（秒），默认使用 default_timeout
            env: 环境变量字典，默认继承系统环境变量
            check_permission: 是否检查权限
            permission: 需要的权限代码

        Returns:
            执行结果字典，包含：
            - success: bool
            - output: str
            - error: Optional[str]
            - exit_code: int
            - execution_mode: str
            - command: str
            - timeout: int
        """
        # 权限检查
        if check_permission:
            check_tool_permission(db, user_id, permission, raise_exception=True)

        # 设置超时
        timeout = timeout or self.default_timeout

        # 设置环境变量
        command_env = os.environ.copy()
        if env:
            command_env.update(env)

        logger.info(f"Executing command: {command}")

        try:
            # 执行命令
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True,
                env=command_env
            )

            # 等待命令完成（带超时）
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()  # 等待进程真正结束，避免僵尸进程

                # 记录命令历史
                self._record_command(command, -1, "", f"Timeout after {timeout}s", timeout)

                raise CommandTimeoutError(command, timeout)

            # 解码输出
            output = stdout.decode('utf-8') if stdout else ""
            error = stderr.decode('utf-8') if stderr else ""
            exit_code = process.returncode

            success = exit_code == 0

            if not success:
                logger.error(f"Command failed: {error}")
            else:
                logger.info(f"Command succeeded, output length: {len(output)}")

            # 记录命令历史
            self._record_command(command, exit_code, output[:1000], error[:500] if error else "", timeout)

            return {
                "success": success,
                "output": output,
                "error": error if error else None,
                "exit_code": exit_code,
                "execution_mode": "cli",
                "command": command,
                "timeout": timeout,
            }

        except CommandTimeoutError:
            raise
        except Exception as e:
            logger.exception(f"Error executing command: {e}")

            # 记录命令历史
            self._record_command(command, -1, "", str(e), timeout)

            return {
                "success": False,
                "output": "",
                "error": str(e),
                "exit_code": -1,
                "execution_mode": "cli",
                "command": command,
                "timeout": timeout,
            }

    def _record_command(
        self,
        command: str,
        exit_code: int,
        output: str,
        error: str,
        timeout: int
    ):
        """记录命令到历史"""
        record = {
            "command": command,
            "exit_code": exit_code,
            "output": output,
            "error": error,
            "timeout": timeout,
        }
        self.command_history.append(record)

        # 限制历史记录数量
        if len(self.command_history) > 100:
            self.command_history = self.command_history[-100:]

    def get_command_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取命令历史

        Args:
            limit: 返回的记录数量

        Returns:
            命令历史列表（最新的在前）
        """
        return self.command_history[-limit:][::-1]

    def clear_command_history(self):
        """清空命令历史"""
        self.command_history = []


class RedisExecutor(CommandExecutor):
    """redis-cli 命令执行器"""

    # 危险操作模式（禁止）
    DANGEROUS_PATTERNS = [
        r'\bFLUSHALL\b',
        r'\bFLUSHDB\b',
        r'\bDEL\b',
        r'\bSHUTDOWN\b',
        r'\bCONFIG\s+SET\b',
        r'\bSCRIPT\s+KILL\b'
    ]

    def __init__(self, default_timeout: int = 10, host: str = "localhost", port: int = 6379):
        super().__init__(default_timeout)
        self.host = host
        self.port = port

    async def execute(
        self,
        command: str,
        user_id: int,
        db: Session,
        timeout: Optional[int] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行 redis-cli 命令

        Args:
            command: Redis 命令（如 "INFO"）
            user_id: 用户ID
            db: 数据库会话
            timeout: 超时时间
            host: Redis 主机
            port: Redis 端口
            password: Redis 密码
        """
        # 安全检查
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return {
                    "success": False,
                    "output": "",
                    "error": f"Dangerous operation detected: {pattern}. Only read operations are allowed.",
                    "exit_code": -1,
                    "execution_mode": "cli",
                }

        # 构建 redis-cli 命令
        h = host or self.host
        p = port or self.port
        full_command = f"redis-cli -h {h} -p {p}"
        if password:
            full_command += f" -a {password}"
        full_command += f" {command}"

        return await super().execute(
            full_command,
            user_id=user_id,
            db=db,
            timeout=timeout,
            permission="command.execute",
            **kwargs
        )


class MySQLExecutor(CommandExecutor):
    """mysql 命令执行器"""

    # 允许的查询前缀
    ALLOWED_PREFIXES = ['SELECT', 'SHOW', 'DESCRIBE', 'EXPLAIN']

    def __init__(self, default_timeout: int = 30, host: str = "localhost", port: int = 3306):
        super().__init__(default_timeout)
        self.host = host
        self.port = port

    async def execute(
        self,
        query: str,
        user_id: int,
        db: Session,
        timeout: Optional[int] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: str = "root",
        password: Optional[str] = None,
        database: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行 MySQL 查询

        Args:
            query: SQL 查询语句
            user_id: 用户ID
            db: 数据库会话
            timeout: 超时时间
            host: MySQL 主机
            port: MySQL 端口
            user: MySQL 用户名
            password: MySQL 密码
            database: 数据库名
        """
        # 安全检查：只允许 SELECT 和 SHOW 语句
        query_upper = query.strip().upper()
        if not any(query_upper.startswith(prefix) for prefix in self.ALLOWED_PREFIXES):
            return {
                "success": False,
                "output": "",
                "error": "Only SELECT, SHOW, DESCRIBE, and EXPLAIN queries are allowed",
                "exit_code": -1,
                "execution_mode": "cli",
            }

        # 构建 mysql 命令
        h = host or self.host
        p = port or self.port
        full_command = f"mysql -h {h} -P {p} -u {user}"
        if password:
            full_command += f" -p{password}"
        if database:
            full_command += f" {database}"
        full_command += f" -e \"{query}\""

        return await super().execute(
            full_command,
            user_id=user_id,
            db=db,
            timeout=timeout,
            permission="command.execute",
            **kwargs
        )


__all__ = [
    "CommandExecutor",
    "CommandExecutionError",
    "CommandTimeoutError",
    "KubectlExecutor",
    "RedisExecutor",
    "MySQLExecutor",
]
