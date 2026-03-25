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
    def build_command(self, operation: str, **kwargs) -> str:
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

    async def execute(self, operation: str, timeout: int = 30, **kwargs) -> Dict[str, Any]:
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

            # 执行命令
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

    def __init__(self):
        super().__init__("kubectl")

    def build_command(self, operation: str, **kwargs) -> str:
        """构建 kubectl 命令"""
        cmd = f"kubectl {operation}"

        # 添加命名空间
        if "namespace" in kwargs and kwargs["namespace"]:
            namespace = kwargs["namespace"]
            if "-n" not in operation and "--namespace" not in operation and "-A" not in operation:
                cmd += f" -n {namespace}"

        # 添加标签选择器
        if "label_selector" in kwargs and kwargs["label_selector"]:
            cmd += f" -l {kwargs['label_selector']}"

        # 添加字段选择器
        if "field_selector" in kwargs and kwargs["field_selector"]:
            cmd += f" --field-selector={kwargs['field_selector']}"

        # 添加 JSON 输出格式
        cmd += " -o json"

        return cmd

    def parse_output(self, stdout: str, stderr: str) -> Any:
        """解析 kubectl 输出"""
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"raw": stdout}


class PrometheusFallback(FallbackExecutor):
    """Prometheus CLI 降级执行器"""

    def __init__(self):
        super().__init__("promql")

    def build_command(self, operation: str, **kwargs) -> str:
        """构建 promql 查询命令"""
        if operation == "query":
            query = kwargs.get("query", "")
            time = kwargs.get("time", "")

            cmd = f"promql query '{query}'"
            if time:
                cmd += f" --time='{time}'"

            return cmd
        elif operation == "query_range":
            query = kwargs.get("query", "")
            start = kwargs.get("start", "")
            end = kwargs.get("end", "")
            step = kwargs.get("step", "1m")

            return f"promql query-range '{query}' --start='{start}' --end='{end}' --step='{step}'"

        return f"promql {operation}"

    def parse_output(self, stdout: str, stderr: str) -> Any:
        """解析 promql 输出"""
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"raw": stdout}


class LokiFallback(FallbackExecutor):
    """Loki CLI 降级执行器"""

    def __init__(self):
        super().__init__("logcli")

    def build_command(self, operation: str, **kwargs) -> str:
        """构建 logcli 查询命令"""
        if operation == "query":
            query = kwargs.get("query", "")
            limit = kwargs.get("limit", "100")

            return f"logcli query --limit={limit} '{query}'"
        elif operation == "query_range":
            query = kwargs.get("query", "")
            start = kwargs.get("start", "")
            end = kwargs.get("end", "")

            return f"logcli query --start='{start}' --end='{end}' '{query}'"

        return f"logcli {operation}"

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
