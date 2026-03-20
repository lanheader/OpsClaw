# app/tools/tool_wrapper.py
"""工具包装器 - 实现工具降级机制

优先使用 SDK 工具，失败时自动降级到命令行工具
"""

from typing import Dict, Any, Optional, Callable, Awaitable
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ToolExecutionMode(Enum):
    """工具执行模式"""

    SDK = "sdk"  # 使用 SDK（如 kubernetes Python 客户端）
    CLI = "cli"  # 使用命令行工具（如 kubectl）
    FALLBACK = "fallback"  # 降级模式


class ToolExecutionResult:
    """工具执行结果"""

    def __init__(
        self,
        success: bool,
        data: Any = None,
        error: Optional[str] = None,
        mode: ToolExecutionMode = ToolExecutionMode.SDK,
        needs_fallback: bool = False,
        fallback_suggestion: Optional[str] = None,
    ):
        self.success = success
        self.data = data
        self.error = error
        self.mode = mode
        self.needs_fallback = needs_fallback
        self.fallback_suggestion = fallback_suggestion

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            "success": self.success,
            "execution_mode": self.mode.value,
        }

        if self.data is not None:
            result["data"] = self.data

        if self.error:
            result["error"] = self.error

        if self.needs_fallback:
            result["needs_fallback"] = True
            result["fallback_suggestion"] = self.fallback_suggestion

        return result


class ToolWrapper:
    """
    工具包装器 - 实现自动降级机制

    使用方式：
    1. 优先尝试 SDK 工具
    2. 如果 SDK 工具失败（未配置、连接失败等），返回降级建议
    3. Agent 收到降级建议后，生成命令行命令
    4. 使用命令行工具执行
    """

    def __init__(
        self,
        name: str,
        sdk_func: Optional[Callable] = None,
        cli_func: Optional[Callable] = None,
        fallback_command_template: Optional[str] = None,
    ):
        """
        初始化工具包装器

        Args:
            name: 工具名称
            sdk_func: SDK 函数（可选）
            cli_func: 命令行函数（可选）
            fallback_command_template: 降级命令模板（可选）
        """
        self.name = name
        self.sdk_func = sdk_func
        self.cli_func = cli_func
        self.fallback_command_template = fallback_command_template

    async def execute(
        self, prefer_mode: ToolExecutionMode = ToolExecutionMode.SDK, **kwargs
    ) -> ToolExecutionResult:
        """
        执行工具

        Args:
            prefer_mode: 优先执行模式
            **kwargs: 工具参数

        Returns:
            ToolExecutionResult
        """
        # 1. 优先尝试 SDK 模式
        if prefer_mode == ToolExecutionMode.SDK and self.sdk_func:
            try:
                logger.info(f"[{self.name}] 尝试使用 SDK 模式执行")

                # 执行 SDK 函数
                if asyncio.iscoroutinefunction(self.sdk_func):
                    result = await self.sdk_func(**kwargs)
                else:
                    result = self.sdk_func(**kwargs)

                # 检查结果是否表示未配置或失败
                if self._is_sdk_unavailable(result):
                    logger.warning(f"[{self.name}] SDK 不可用，建议降级到命令行")
                    return self._create_fallback_result(kwargs)

                logger.info(f"[{self.name}] SDK 执行成功")
                return ToolExecutionResult(success=True, data=result, mode=ToolExecutionMode.SDK)

            except Exception as e:
                logger.warning(f"[{self.name}] SDK 执行失败: {e}，建议降级到命令行")
                return self._create_fallback_result(kwargs, error=str(e))

        # 2. 降级到命令行模式
        if self.cli_func:
            try:
                logger.info(f"[{self.name}] 使用命令行模式执行")

                # 执行命令行函数
                if asyncio.iscoroutinefunction(self.cli_func):
                    result = await self.cli_func(**kwargs)
                else:
                    result = self.cli_func(**kwargs)

                logger.info(f"[{self.name}] 命令行执行成功")
                return ToolExecutionResult(success=True, data=result, mode=ToolExecutionMode.CLI)

            except Exception as e:
                logger.error(f"[{self.name}] 命令行执行失败: {e}")
                return ToolExecutionResult(
                    success=False, error=f"命令行执行失败: {str(e)}", mode=ToolExecutionMode.CLI
                )

        # 3. 没有可用的执行方式
        logger.error(f"[{self.name}] 没有可用的执行方式")
        return ToolExecutionResult(
            success=False, error="没有可用的工具执行方式", mode=ToolExecutionMode.SDK
        )

    def _is_sdk_unavailable(self, result: Any) -> bool:
        """
        检查 SDK 结果是否表示不可用

        Args:
            result: SDK 执行结果

        Returns:
            bool: 是否不可用
        """
        # 如果结果是字典，检查是否包含错误标记
        if isinstance(result, dict):
            # 检查是否有明确的错误标记
            if result.get("error") or result.get("unavailable"):
                return True

            # 检查是否是模拟数据（表示未配置）
            if result.get("_mock_data") or result.get("_simulated"):
                return True

        return False

    def _create_fallback_result(
        self, kwargs: Dict[str, Any], error: Optional[str] = None
    ) -> ToolExecutionResult:
        """
        创建降级结果

        Args:
            kwargs: 原始参数
            error: 错误信息

        Returns:
            ToolExecutionResult
        """
        # 生成降级建议
        if self.fallback_command_template:
            suggestion = self.fallback_command_template.format(**kwargs)
        else:
            suggestion = f"请使用命令行工具执行 {self.name}"

        error_msg = error or "SDK 工具不可用或未配置"

        return ToolExecutionResult(
            success=False,
            error=error_msg,
            mode=ToolExecutionMode.SDK,
            needs_fallback=True,
            fallback_suggestion=suggestion,
        )


# 导入 asyncio（用于检查协程）
import asyncio
