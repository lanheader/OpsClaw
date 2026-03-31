# app/tools/command_executor_tools.py
"""
命令执行工具 - 用于执行系统命令并返回结果

安全加固说明（v3.4）：
1. 移除 shell=True，使用参数列表防止命令注入
2. 敏感信息（密码）通过环境变量传递，避免在 ps 中泄露
3. 收紧 /proc/ 访问白名单，防止密钥泄露
"""
from typing import Dict, Any, Optional, List
from langchain_core.tools import tool
import asyncio
import os
import re
import shlex

from app.utils.logger import get_logger, get_request_context

logger = get_logger(__name__)


def _log_tool_start(tool_name: str, **kwargs):
    """记录工具开始执行的日志"""
    ctx = get_request_context()
    session_id = ctx.get('session_id', 'no-sess')
    params = {k: v for k, v in kwargs.items() if v is not None}
    logger.info(f"🔧 [{session_id}] 执行工具: {tool_name} | 参数: {params}")


def _log_tool_success(tool_name: str, message: str = None):
    """记录工具执行成功的日志"""
    ctx = get_request_context()
    session_id = ctx.get('session_id', 'no-sess')
    if message:
        logger.info(f"✅ [{session_id}] 工具完成: {tool_name} | {message}")
    else:
        logger.info(f"✅ [{session_id}] 工具完成: {tool_name}")


def _log_tool_error(tool_name: str, error: str):
    """记录工具执行失败的日志"""
    ctx = get_request_context()
    session_id = ctx.get('session_id', 'no-sess')
    logger.error(f"❌ [{session_id}] 工具失败: {tool_name} | 错误: {error}")


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
    _log_tool_start("execute_redis_command", command=command, host=host, port=port)

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
            error_msg = f"危险操作被拒绝: {pattern}。只允许只读操作。"
            _log_tool_error("execute_redis_command", error_msg)
            return {
                "success": False,
                "output": "",
                "error": error_msg,
                "error_type": "SecurityViolation",
                "suggestion": "请使用只读命令（如 INFO, GET, KEYS）来查询数据",
                "exit_code": -1,
                "execution_mode": "cli",
                "needs_fallback": False
            }

    # 构建参数列表（避免 shell=True 命令注入）
    cmd_args = ["redis-cli", "-h", host, "-p", str(port)]

    # 环境变量传递密码（避免在 ps 中泄露）
    env = os.environ.copy()
    if password:
        env["REDISCLI_AUTH"] = password

    # 解析 Redis 命令为参数列表
    # 例如 "INFO memory" -> ["INFO", "memory"]
    command_parts = shlex.split(command)
    cmd_args.extend(command_parts)

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
            error_msg = f"命令执行超时（{timeout}秒）"
            _log_tool_error("execute_redis_command", error_msg)
            return {
                "success": False,
                "output": "",
                "error": error_msg,
                "error_type": "Timeout",
                "suggestion": "请增加超时时间或简化查询",
                "exit_code": -1,
                "execution_mode": "cli",
                "needs_fallback": False
            }

        output = stdout.decode('utf-8') if stdout else ""
        error = stderr.decode('utf-8') if stderr else ""
        exit_code = process.returncode

        success = exit_code == 0

        if success:
            _log_tool_success("execute_redis_command", f"Redis 命令执行成功")
        else:
            _log_tool_error("execute_redis_command", error or f"退出码: {exit_code}")

        return {
            "success": success,
            "output": output,
            "error": error if error else None,
            "error_type": "CommandFailed" if not success and error else None,
            "suggestion": "请检查 Redis 服务是否运行，以及命令语法是否正确" if not success else None,
            "exit_code": exit_code,
            "execution_mode": "cli",
            "needs_fallback": False
        }

    except FileNotFoundError:
        error_msg = "redis-cli 命令未找到"
        _log_tool_error("execute_redis_command", error_msg)
        return {
            "success": False,
            "output": "",
            "error": error_msg,
            "error_type": "CommandNotFound",
            "suggestion": "请确保已安装 Redis 客户端工具",
            "exit_code": -1,
            "execution_mode": "cli",
            "needs_fallback": False
        }
    except Exception as e:
        error_msg = str(e)
        _log_tool_error("execute_redis_command", error_msg)
        return {
            "success": False,
            "output": "",
            "error": error_msg,
            "error_type": type(e).__name__,
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
    _log_tool_start("execute_mysql_query", query=query[:100], host=host, database=database)

    # 安全检查：只允许 SELECT 和 SHOW 语句
    query_upper = query.strip().upper()
    allowed_prefixes = ['SELECT', 'SHOW', 'DESCRIBE', 'EXPLAIN']

    if not any(query_upper.startswith(prefix) for prefix in allowed_prefixes):
        error_msg = "只允许 SELECT, SHOW, DESCRIBE, 和 EXPLAIN 查询"
        _log_tool_error("execute_mysql_query", error_msg)
        return {
            "success": False,
            "output": "",
            "error": error_msg,
            "error_type": "SecurityViolation",
            "suggestion": "请使用只读查询语句",
            "exit_code": -1,
            "execution_mode": "cli",
            "needs_fallback": False
        }

    # 构建参数列表（避免 shell=True 命令注入）
    cmd_args = ["mysql", "-h", host, "-P", str(port), "-u", user]

    # 环境变量传递密码（避免在 ps 中泄露）
    env = os.environ.copy()
    if password:
        env["MYSQL_PWD"] = password

    if database:
        cmd_args.append(database)

    cmd_args.extend(["-e", query])

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
            error_msg = f"查询执行超时（{timeout}秒）"
            _log_tool_error("execute_mysql_query", error_msg)
            return {
                "success": False,
                "output": "",
                "error": error_msg,
                "error_type": "Timeout",
                "suggestion": "请增加超时时间或优化查询",
                "exit_code": -1,
                "execution_mode": "cli",
                "needs_fallback": False
            }

        output = stdout.decode('utf-8') if stdout else ""
        error = stderr.decode('utf-8') if stderr else ""
        exit_code = process.returncode

        success = exit_code == 0

        if success:
            _log_tool_success("execute_mysql_query", "MySQL 查询执行成功")
        else:
            _log_tool_error("execute_mysql_query", error or f"退出码: {exit_code}")

        return {
            "success": success,
            "output": output,
            "error": error if error else None,
            "error_type": "QueryFailed" if not success and error else None,
            "suggestion": "请检查 MySQL 服务是否运行，SQL 语法是否正确" if not success else None,
            "exit_code": exit_code,
            "execution_mode": "cli",
            "needs_fallback": False
        }

    except FileNotFoundError:
        error_msg = "mysql 命令未找到"
        _log_tool_error("execute_mysql_query", error_msg)
        return {
            "success": False,
            "output": "",
            "error": error_msg,
            "error_type": "CommandNotFound",
            "suggestion": "请确保已安装 MySQL 客户端工具",
            "exit_code": -1,
            "execution_mode": "cli",
            "needs_fallback": False
        }
    except Exception as e:
        error_msg = str(e)
        _log_tool_error("execute_mysql_query", error_msg)
        return {
            "success": False,
            "output": "",
            "error": error_msg,
            "error_type": type(e).__name__,
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
    _log_tool_start("execute_safe_shell_command", command=command)

    # 默认白名单：只允许安全的读取命令
    default_allowed = [
        'uptime', 'df', 'free', 'top', 'ps', 'netstat',
        'ss', 'lsof', 'vmstat', 'iostat', 'sar',
        'systemctl status', 'journalctl', 'dmesg',
        'ls', 'pwd', 'whoami', 'hostname',
        'date', 'uname', 'which', 'whereis'
    ]

    # /proc/ 允许的安全路径白名单（防止泄露密钥）
    PROC_SAFE_PATHS = [
        '/proc/cpuinfo',
        '/proc/meminfo',
        '/proc/loadavg',
        '/proc/uptime',
        '/proc/version',
        '/proc/filesystems',
        '/proc/mounts',
        '/proc/diskstats',
        '/proc/net/dev',
        '/proc/net/tcp',
        '/proc/sys/',
    ]

    # 危险的 /proc/ 路径模式（绝对禁止）
    DANGEROUS_PROC_PATTERNS = [
        r'/proc/self/',           # 当前进程信息，可能泄露 environ
        r'/proc/\d+/environ',     # 任意进程的环境变量
        r'/proc/\d+/fd/',         # 文件描述符
        r'/proc/\d+/cmdline',     # 命令行参数
        r'/proc/\d+/maps',        # 内存映射
    ]

    if allowed_commands is None:
        allowed_commands = default_allowed

    # 解析命令，检查是否是 cat /proc/ 类型的命令
    command_parts = command.split()
    command_base = command_parts[0] if command_parts else ""

    # 特殊处理 cat /proc/ 类命令
    if command_base == 'cat' and len(command_parts) > 1:
        proc_path = command_parts[1]

        # 检查是否是危险的 /proc/ 路径
        for pattern in DANGEROUS_PROC_PATTERNS:
            if re.search(pattern, proc_path):
                error_msg = f"禁止访问敏感 /proc/ 路径: {proc_path}"
                _log_tool_error("execute_safe_shell_command", error_msg)
                return {
                    "success": False,
                    "output": "",
                    "error": error_msg,
                    "error_type": "SecurityViolation",
                    "suggestion": "只允许访问 /proc/cpuinfo, /proc/meminfo 等安全路径",
                    "exit_code": -1,
                    "execution_mode": "cli",
                    "needs_fallback": False
                }

        # 检查是否在安全白名单中
        is_safe_proc = False
        for safe_path in PROC_SAFE_PATHS:
            if proc_path.startswith(safe_path):
                is_safe_proc = True
                break

        if proc_path.startswith('/proc/') and not is_safe_proc:
            error_msg = f"/proc/ 路径不在白名单中: {proc_path}"
            _log_tool_error("execute_safe_shell_command", error_msg)
            return {
                "success": False,
                "output": "",
                "error": error_msg,
                "error_type": "SecurityViolation",
                "suggestion": f"允许的 /proc/ 路径: {', '.join(PROC_SAFE_PATHS[:5])}...",
                "exit_code": -1,
                "execution_mode": "cli",
                "needs_fallback": False
            }

        # 如果是安全的 /proc/ 路径，允许执行
        if is_safe_proc:
            is_allowed = True
        else:
            is_allowed = False
    else:
        # 普通命令检查白名单（只匹配命令名，防止 ; && | 绕过）
        command_parts = command.split()
        command_name = command_parts[0] if command_parts else ""
        is_allowed = command_name in allowed_commands

    if not is_allowed:
        error_msg = f"命令 '{command_base}' 不在允许列表中"
        _log_tool_error("execute_safe_shell_command", error_msg)
        return {
            "success": False,
            "output": "",
            "error": error_msg,
            "error_type": "NotAllowed",
            "suggestion": f"允许的命令: {', '.join(allowed_commands[:10])}...",
            "exit_code": -1,
            "execution_mode": "cli",
            "needs_fallback": False
        }

    # 额外的危险模式检查（包括命令链接符）
    dangerous_patterns = [
        r'\brm\b', r'\bmv\b', r'\bcp\b.*>',
        r'>', r'>>', r'\|.*rm', r'\|.*mv',
        r'sudo', r'su\b', r'chmod', r'chown',
        r';', r'&&', r'\|\|',  # 命令链接符
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, command):
            error_msg = f"检测到危险模式: {pattern}"
            _log_tool_error("execute_safe_shell_command", error_msg)
            return {
                "success": False,
                "output": "",
                "error": error_msg,
                "error_type": "DangerousPattern",
                "suggestion": "此命令被安全策略禁止",
                "exit_code": -1,
                "execution_mode": "cli",
                "needs_fallback": False
            }

    try:
        # 使用参数列表执行命令（避免 shell=True 命令注入）
        cmd_args = shlex.split(command)

        # 获取当前环境变量
        env = os.environ.copy()

        process = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
            error_msg = f"命令执行超时（{timeout}秒）"
            _log_tool_error("execute_safe_shell_command", error_msg)
            return {
                "success": False,
                "output": "",
                "error": error_msg,
                "error_type": "Timeout",
                "suggestion": "请增加超时时间或简化命令",
                "exit_code": -1,
                "execution_mode": "cli",
                "needs_fallback": False
            }

        output = stdout.decode('utf-8') if stdout else ""
        error = stderr.decode('utf-8') if stderr else ""
        exit_code = process.returncode

        success = exit_code == 0

        if success:
            _log_tool_success("execute_safe_shell_command", "Shell 命令执行成功")
        else:
            _log_tool_error("execute_safe_shell_command", error or f"退出码: {exit_code}")

        return {
            "success": success,
            "output": output,
            "error": error if error else None,
            "error_type": "CommandFailed" if not success and error else None,
            "suggestion": None if success else "请检查命令语法和参数",
            "exit_code": exit_code,
            "execution_mode": "cli",
            "needs_fallback": False
        }

    except Exception as e:
        error_msg = str(e)
        _log_tool_error("execute_safe_shell_command", error_msg)
        return {
            "success": False,
            "output": "",
            "error": error_msg,
            "error_type": type(e).__name__,
            "exit_code": -1,
            "execution_mode": "cli",
            "needs_fallback": False
        }
