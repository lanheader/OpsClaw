"""
CLI 降级机制

当 SDK 不可用时，使用 CLI 命令作为降级方案。
作为内部降级使用，不直接暴露给 agent。
"""

import asyncio
import json
import logging
import os
import re
import shlex
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class FallbackExecutor(ABC):
    """
    CLI 降级执行器基类

    当 SDK 不可用时，使用 CLI 命令作为降级方案。
    """

    def __init__(self, command_prefix: str):
        """
        初始化降级执行器

        Args:
            command_prefix: 命令前缀（如 "kubectl", "promql", "logcli"）
        """
        self.command_prefix = command_prefix

    @abstractmethod
    def build_command(self, operation: str, **kwargs) -> str:  # type: ignore[no-untyped-def]
        """
        构建 CLI 命令

        Args:
            operation: 操作类型（如 "get pods", "query"）
            **kwargs: 操作参数

        Returns:
            完整的 CLI 命令字符串
        """
        pass

    @abstractmethod
    def parse_output(self, stdout: str, stderr: str) -> Dict[str, Any]:
        """
        解析 CLI 输出

        Args:
            stdout: 标准输出
            stderr: 标准错误输出

        Returns:
            解析后的数据字典
        """
        pass

    async def execute(self, operation: str, timeout: int = 30, **kwargs) -> Dict[str, Any]:  # type: ignore[no-untyped-def]
        """
        执行 CLI 命令

        Args:
            operation: 操作类型
            timeout: 超时时间（秒）
            **kwargs: 操作参数

        Returns:
            {
                "success": bool,
                "data": Any,
                "error": str (可选),
                "execution_mode": "cli",
                "command": str (执行的命令)
            }
        """
        # 构建命令
        command = self.build_command(operation, **kwargs)

        logger.info(f"Executing CLI command: {command}")

        try:
            # 获取环境变量
            env = os.environ.copy()

            # 执行命令（使用 shlex.split 避免 shell 注入）
            process = await asyncio.create_subprocess_exec(
                *shlex.split(command),
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
                await process.wait()
                return {
                    "success": False,
                    "error": f"Command timed out after {timeout} seconds",
                    "execution_mode": "cli",
                    "command": command
                }

            # 解码输出
            stdout_str = stdout.decode('utf-8') if stdout else ""
            stderr_str = stderr.decode('utf-8') if stderr else ""

            success = process.returncode == 0

            if success:
                data = self.parse_output(stdout_str, stderr_str)
                return {
                    "success": True,
                    "data": data,
                    "execution_mode": "cli",
                    "command": command
                }
            else:
                return {
                    "success": False,
                    "error": stderr_str or stdout_str,
                    "execution_mode": "cli",
                    "command": command
                }

        except Exception as e:
            logger.exception(f"Error executing CLI command: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_mode": "cli",
                "command": command
            }


class K8sFallback(FallbackExecutor):
    """K8s CLI 降级执行器"""

    def __init__(self):  # type: ignore[no-untyped-def]
        super().__init__("kubectl")

    def build_command(self, operation: str, **kwargs) -> str:  # type: ignore[no-untyped-def]
        """构建 kubectl 命令（使用 shlex.quote 转义用户参数）"""
        parts = ["kubectl", operation]

        # 添加命名空间
        if "namespace" in kwargs and kwargs["namespace"]:
            namespace = kwargs["namespace"]
            if "-n" not in operation and "--namespace" not in operation and "-A" not in operation:
                parts.extend(["-n", shlex.quote(namespace)])

        # 添加标签选择器
        if "label_selector" in kwargs and kwargs["label_selector"]:
            parts.extend(["-l", shlex.quote(kwargs['label_selector'])])

        # 添加字段选择器
        if "field_selector" in kwargs and kwargs["field_selector"]:
            parts.append(f"--field-selector={shlex.quote(kwargs['field_selector'])}")

        # 添加 JSON 输出格式
        parts.append("-o json")

        return " ".join(parts)

    def parse_output(self, stdout: str, stderr: str) -> Any:
        """解析 kubectl 输出"""
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"raw": stdout}


class PrometheusFallback(FallbackExecutor):
    """Prometheus CLI 降级执行器"""

    def __init__(self):  # type: ignore[no-untyped-def]
        super().__init__("promql")

    def build_command(self, operation: str, **kwargs) -> str:  # type: ignore[no-untyped-def]
        """构建 promql 查询命令（使用 shlex.quote 转义用户参数）"""
        if operation == "query":
            query = kwargs.get("query", "")
            time_val = kwargs.get("time", "")

            cmd = f"promql query {shlex.quote(query)}"
            if time_val:
                cmd += f" --time={shlex.quote(time_val)}"

            return cmd
        elif operation == "query_range":
            query = kwargs.get("query", "")
            start = kwargs.get("start", "")
            end = kwargs.get("end", "")
            step = kwargs.get("step", "1m")

            return f"promql query-range {shlex.quote(query)} --start={shlex.quote(start)} --end={shlex.quote(end)} --step={shlex.quote(step)}"

        return f"promql {shlex.quote(operation)}"

    async def execute(self, operation: str, timeout: int = 30, **kwargs) -> Dict[str, Any]:  # type: ignore[no-untyped-def]
        """
        执行 CLI 命令（带详细日志）
        """
        # 构建命令
        command = self.build_command(operation, **kwargs)

        logger.info(f"🔧 [Prometheus CLI] 执行命令: {command}")
        logger.debug(f"🔧 [Prometheus CLI] 参数: operation={operation}, kwargs={kwargs}")

        try:
            # 获取环境变量
            env = os.environ.copy()

            # 执行命令（使用 shlex.split 避免 shell 注入）
            process = await asyncio.create_subprocess_exec(
                *shlex.split(command),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )

                # 记录原始输出
                logger.debug(f"📤 [Prometheus CLI] stdout: {stdout[:500] if stdout else '(empty)'}")  # type: ignore[str-bytes-safe]
                logger.debug(f"📤 [Prometheus CLI] stderr: {stderr[:500] if stderr else '(empty)'}")  # type: ignore[str-bytes-safe]

                # 检查返回码
                returncode = process.returncode
                if returncode != 0:
                    logger.error(f"❌ [Prometheus CLI] 命令失败 (退出码: {returncode}):")
                    logger.error(f"   stderr: {stderr}")  # type: ignore[str-bytes-safe]
                    return {
                        "success": False,
                        "error": f"CLI command failed with exit code {returncode}: {stderr}",  # type: ignore[str-bytes-safe]
                        "execution_mode": "cli",
                        "command": command,
                        "returncode": returncode
                    }

                # 解析输出
                result = self.parse_output(stdout, stderr)  # type: ignore[arg-type]
                logger.info(f"✅ [Prometheus CLI] 命令执行成功")
                logger.debug(f"📊 [Prometheus CLI] 解析结果: {str(result)[:200]}...")

                return {
                    "success": True,
                    "data": result,
                    "execution_mode": "cli",
                    "command": command
                }

            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                logger.error(f"⏱️  [Prometheus CLI] 命令超时 (>{timeout}秒)")
                return {
                    "success": False,
                    "error": f"Command timed out after {timeout} seconds",
                    "execution_mode": "cli",
                    "command": command
                }

        except Exception as e:
            logger.exception(f"❌ [Prometheus CLI] 执行异常: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_mode": "cli",
                "command": command
            }

    def parse_output(self, stdout: str, stderr: str) -> Any:
        """解析 promql 输出（由自定义 execute 方法处理，此方法为抽象类接口要求）"""
        # 注意：PrometheusFallback 使用自定义 execute 方法，不使用此方法
        # 但必须实现以满足抽象基类要求
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"raw": stdout}


class LokiFallback(FallbackExecutor):
    """Loki CLI 降级执行器"""

    def __init__(self):  # type: ignore[no-untyped-def]
        super().__init__("logcli")

    def build_command(self, operation: str, **kwargs) -> str:  # type: ignore[no-untyped-def]
        """构建 logcli 查询命令（使用 shlex.quote 转义用户参数）"""
        if operation == "query":
            query = kwargs.get("query", "")
            limit = kwargs.get("limit", "100")

            return f"logcli query --limit={shlex.quote(str(limit))} {shlex.quote(query)}"
        elif operation == "query_range":
            query = kwargs.get("query", "")
            start = kwargs.get("start", "")
            end = kwargs.get("end", "")

            return f"logcli query --start={shlex.quote(start)} --end={shlex.quote(end)} {shlex.quote(query)}"

        return f"logcli {shlex.quote(operation)}"

    def parse_output(self, stdout: str, stderr: str) -> Any:
        """解析 logcli 输出"""
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"raw": stdout}


# 全局降级执行器实例
_k8s_fallback: Optional[K8sFallback] = None
_prometheus_fallback: Optional[PrometheusFallback] = None
_loki_fallback: Optional[LokiFallback] = None


def get_k8s_fallback() -> K8sFallback:
    """获取 K8s 降级执行器"""
    global _k8s_fallback
    if _k8s_fallback is None:
        _k8s_fallback = K8sFallback()
    return _k8s_fallback


def get_prometheus_fallback() -> PrometheusFallback:
    """获取 Prometheus 降级执行器"""
    global _prometheus_fallback
    if _prometheus_fallback is None:
        _prometheus_fallback = PrometheusFallback()
    return _prometheus_fallback


def get_loki_fallback() -> LokiFallback:
    """获取 Loki 降级执行器"""
    global _loki_fallback
    if _loki_fallback is None:
        _loki_fallback = LokiFallback()
    return _loki_fallback


__all__ = [
    "FallbackExecutor",
    "K8sFallback",
    "PrometheusFallback",
    "LokiFallback",
    "get_k8s_fallback",
    "get_prometheus_fallback",
    "get_loki_fallback",
]
