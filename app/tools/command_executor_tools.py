# app/tools/command_executor_tools.py
"""命令执行工具 - 用于执行系统命令并返回结果"""
from typing import Dict, Any, Optional, List
from langchain_core.tools import tool
import asyncio
import logging
import os
import re

logger = logging.getLogger(__name__)


@tool
async def execute_kubectl_command(
    command: str,
    namespace: Optional[str] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    执行 kubectl 命令并返回结果。

    参数：
        command: kubectl 子命令（如 "get pods", "describe pod xxx"）
        namespace: 可选的命名空间（如果提供，会自动添加 -n 参数）
        timeout: 命令超时时间（秒）

    返回：
        包含以下内容的字典：
        - success: bool（命令是否成功执行）
        - output: str（命令输出）
        - error: Optional[str]（错误信息）
        - exit_code: int（退出码）
        - execution_mode: str（执行模式，固定为 "cli"）
        - needs_fallback: bool（是否需要降级，CLI 工具固定为 False）

    示例：
        # 查看所有 Pod
        result = await execute_kubectl_command.ainvoke({
            "command": "get pods -A"
        })

        # 查看特定命名空间的 Pod
        result = await execute_kubectl_command.ainvoke({
            "command": "get pods",
            "namespace": "production"
        })

        # 查看 Pod 详情
        result = await execute_kubectl_command.ainvoke({
            "command": "describe pod my-pod",
            "namespace": "default"
        })
    """
    # 安全检查：只允许读取操作
    dangerous_patterns = [
        r'\bdelete\b',
        r'\bremove\b',
        r'\brm\b',
        r'\bapply\b',
        r'\bcreate\b',
        r'\bedit\b',
        r'\bpatch\b',
        r'\breplace\b',
        r'\bexec\b',
        r'\battach\b',
        r'\bcp\b'
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return {
                "success": False,
                "output": "",
                "error": f"Dangerous operation detected: {pattern}. Only read operations are allowed.",
                "exit_code": -1,
                "execution_mode": "cli",
                "needs_fallback": False
            }

    # 构建完整命令
    # 检查命令是否已经包含 kubectl
    if command.strip().startswith('kubectl'):
        # 命令已经包含 kubectl，直接使用
        full_command = command
        if namespace and "-n" not in command and "--namespace" not in command and "-A" not in command:
            # 在 kubectl 后面插入 namespace
            full_command = command.replace('kubectl', f'kubectl -n {namespace}', 1)
    else:
        # 命令不包含 kubectl，添加前缀
        full_command = f"kubectl {command}"
        if namespace and "-n" not in command and "--namespace" not in command and "-A" not in command:
            full_command = f"kubectl -n {namespace} {command}"

    logger.info(f"Executing kubectl command: {full_command}")

    try:
        # 获取当前环境变量（继承系统环境）
        env = os.environ.copy()

        # 执行命令（继承环境变量）
        process = await asyncio.create_subprocess_shell(
            full_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True,
            env=env  # 传递环境变量
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
            return {
                "success": False,
                "output": "",
                "error": f"Command timed out after {timeout} seconds",
                "exit_code": -1,
                "execution_mode": "cli",
                "needs_fallback": False
            }

        # 解码输出
        output = stdout.decode('utf-8') if stdout else ""
        error = stderr.decode('utf-8') if stderr else ""
        exit_code = process.returncode

        success = exit_code == 0

        if not success:
            logger.error(f"kubectl command failed: {error}")
        else:
            logger.info(f"kubectl command succeeded, output length: {len(output)}")

        return {
            "success": success,
            "output": output,
            "error": error if error else None,
            "exit_code": exit_code,
            "execution_mode": "cli",
            "needs_fallback": False
        }

    except Exception as e:
        logger.exception(f"Error executing kubectl command: {e}")
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "exit_code": -1,
            "execution_mode": "cli",
            "needs_fallback": False
        }


@tool
async def execute_redis_command(
    command: str,
    host: str = "localhost",
    port: int = 6379,
    password: Optional[str] = None,
    timeout: int = 10
) -> Dict[str, Any]:
    """
    执行 redis-cli 命令并返回结果。

    参数：
        command: Redis 命令（如 "INFO", "GET key", "KEYS pattern"）
        host: Redis 主机地址
        port: Redis 端口
        password: 可选的 Redis 密码
        timeout: 命令超时时间（秒）

    返回：
        包含以下内容的字典：
        - success: bool
        - output: str
        - error: Optional[str]
        - exit_code: int
        - execution_mode: str（执行模式，固定为 "cli"）
        - needs_fallback: bool（是否需要降级，CLI 工具固定为 False）

    示例：
        # 查看 Redis 信息
        result = await execute_redis_command.ainvoke({
            "command": "INFO memory"
        })

        # 查看所有 key
        result = await execute_redis_command.ainvoke({
            "command": "KEYS *"
        })
    """
    # 安全检查：禁止危险操作
    dangerous_patterns = [
        r'\bFLUSHALL\b',
        r'\bFLUSHDB\b',
        r'\bDEL\b',
        r'\bSHUTDOWN\b',
        r'\bCONFIG\s+SET\b',
        r'\bSCRIPT\s+KILL\b'
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return {
                "success": False,
                "output": "",
                "error": f"Dangerous operation detected: {pattern}. Only read operations are allowed.",
                "exit_code": -1,
                "execution_mode": "cli",
                "needs_fallback": False
            }

    # 构建 redis-cli 命令
    full_command = f"redis-cli -h {host} -p {port}"
    if password:
        full_command += f" -a {password}"
    full_command += f" {command}"

    logger.info(f"Executing redis command: redis-cli -h {host} -p {port} {command}")

    try:
        # 获取当前环境变量
        env = os.environ.copy()

        process = await asyncio.create_subprocess_shell(
            full_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True,
            env=env
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()  # 等待进程真正结束，避免僵尸进程
            return {
                "success": False,
                "output": "",
                "error": f"Command timed out after {timeout} seconds",
                "exit_code": -1,
                "execution_mode": "cli",
                "needs_fallback": False
            }

        output = stdout.decode('utf-8') if stdout else ""
        error = stderr.decode('utf-8') if stderr else ""
        exit_code = process.returncode

        success = exit_code == 0

        return {
            "success": success,
            "output": output,
            "error": error if error else None,
            "exit_code": exit_code,
            "execution_mode": "cli",
            "needs_fallback": False
        }

    except Exception as e:
        logger.exception(f"Error executing redis command: {e}")
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "exit_code": -1,
            "execution_mode": "cli",
            "needs_fallback": False
        }


@tool
async def execute_mysql_query(
    query: str,
    host: str = "localhost",
    port: int = 3306,
    user: str = "root",
    password: Optional[str] = None,
    database: Optional[str] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    执行 MySQL 查询并返回结果。

    参数：
        query: SQL 查询语句
        host: MySQL 主机地址
        port: MySQL 端口
        user: MySQL 用户名
        password: MySQL 密码
        database: 可选的数据库名
        timeout: 查询超时时间（秒）

    返回：
        包含以下内容的字典：
        - success: bool
        - output: str
        - error: Optional[str]
        - exit_code: int
        - execution_mode: str（执行模式，固定为 "cli"）
        - needs_fallback: bool（是否需要降级，CLI 工具固定为 False）

    示例：
        # 查看进程列表
        result = await execute_mysql_query.ainvoke({
            "query": "SHOW PROCESSLIST"
        })

        # 查看慢查询
        result = await execute_mysql_query.ainvoke({
            "query": "SELECT * FROM mysql.slow_log LIMIT 10"
        })
    """
    # 安全检查：只允许 SELECT 和 SHOW 语句
    query_upper = query.strip().upper()
    allowed_prefixes = ['SELECT', 'SHOW', 'DESCRIBE', 'EXPLAIN']

    if not any(query_upper.startswith(prefix) for prefix in allowed_prefixes):
        return {
            "success": False,
            "output": "",
            "error": "Only SELECT, SHOW, DESCRIBE, and EXPLAIN queries are allowed",
            "exit_code": -1,
            "execution_mode": "cli",
            "needs_fallback": False
        }

    # 构建 mysql 命令
    full_command = f"mysql -h {host} -P {port} -u {user}"
    if password:
        full_command += f" -p{password}"
    if database:
        full_command += f" {database}"
    full_command += f" -e \"{query}\""

    logger.info(f"Executing mysql query: {query}")

    try:
        # 获取当前环境变量
        env = os.environ.copy()

        process = await asyncio.create_subprocess_shell(
            full_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True,
            env=env
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()  # 等待进程真正结束，避免僵尸进程
            return {
                "success": False,
                "output": "",
                "error": f"Query timed out after {timeout} seconds",
                "exit_code": -1
            }

        output = stdout.decode('utf-8') if stdout else ""
        error = stderr.decode('utf-8') if stderr else ""
        exit_code = process.returncode

        success = exit_code == 0

        return {
            "success": success,
            "output": output,
            "error": error if error else None,
            "exit_code": exit_code,
            "execution_mode": "cli",
            "needs_fallback": False
        }

    except Exception as e:
        logger.exception(f"Error executing mysql query: {e}")
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "exit_code": -1,
            "execution_mode": "cli",
            "needs_fallback": False
        }


@tool
async def execute_safe_shell_command(
    command: str,
    allowed_commands: Optional[List[str]] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    执行安全的 shell 命令并返回结果。

    只允许执行白名单中的命令，用于执行系统诊断命令。

    参数：
        command: 要执行的 shell 命令
        allowed_commands: 允许的命令白名单（如果为 None，使用默认白名单）
        timeout: 命令超时时间（秒）

    返回：
        包含以下内容的字典：
        - success: bool
        - output: str
        - error: Optional[str]
        - exit_code: int
        - execution_mode: str（执行模式，固定为 "cli"）
        - needs_fallback: bool（是否需要降级，CLI 工具固定为 False）

    示例：
        # 查看系统负载
        result = await execute_safe_shell_command.ainvoke({
            "command": "uptime"
        })

        # 查看磁盘使用
        result = await execute_safe_shell_command.ainvoke({
            "command": "df -h"
        })
    """
    # 默认白名单：只允许安全的读取命令
    default_allowed = [
        'uptime', 'df', 'free', 'top', 'ps', 'netstat',
        'ss', 'lsof', 'vmstat', 'iostat', 'sar',
        'systemctl status', 'journalctl', 'dmesg',
        'cat /proc/', 'ls', 'pwd', 'whoami', 'hostname',
        'date', 'uname', 'which', 'whereis'
    ]

    if allowed_commands is None:
        allowed_commands = default_allowed

    # 检查命令是否在白名单中
    command_base = command.split()[0] if command else ""
    is_allowed = False

    for allowed in allowed_commands:
        if command.startswith(allowed):
            is_allowed = True
            break

    if not is_allowed:
        return {
            "success": False,
            "output": "",
            "error": f"Command '{command_base}' is not in the allowed list. Allowed: {', '.join(allowed_commands)}",
            "exit_code": -1,
            "execution_mode": "cli",
            "needs_fallback": False
        }

    # 额外的危险模式检查
    dangerous_patterns = [
        r'\brm\b', r'\bmv\b', r'\bcp\b.*>',
        r'>', r'>>', r'\|.*rm', r'\|.*mv',
        r'sudo', r'su\b', r'chmod', r'chown'
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, command):
            return {
                "success": False,
                "output": "",
                "error": f"Dangerous pattern detected: {pattern}",
                "exit_code": -1,
                "execution_mode": "cli",
                "needs_fallback": False
            }

    logger.info(f"Executing safe shell command: {command}")

    try:
        # 获取当前环境变量
        env = os.environ.copy()

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True,
            env=env
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()  # 等待进程真正结束，避免僵尸进程
            return {
                "success": False,
                "output": "",
                "error": f"Command timed out after {timeout} seconds",
                "exit_code": -1,
                "execution_mode": "cli",
                "needs_fallback": False
            }

        output = stdout.decode('utf-8') if stdout else ""
        error = stderr.decode('utf-8') if stderr else ""
        exit_code = process.returncode

        success = exit_code == 0

        return {
            "success": success,
            "output": output,
            "error": error if error else None,
            "exit_code": exit_code,
            "execution_mode": "cli",
            "needs_fallback": False
        }

    except Exception as e:
        logger.exception(f"Error executing shell command: {e}")
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "exit_code": -1,
            "execution_mode": "cli",
            "needs_fallback": False
        }
