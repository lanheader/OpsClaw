# app/middleware/dynamic_permission_middleware.py
"""
动态权限中间件

职责：
- 在工具调用前检查当前用户是否有权限
- 无权限的工具调用直接拦截返回错误
- 支持静态传入权限或从请求上下文动态获取

使用方式：
    # 方式1：静态传入权限
    middleware = DynamicPermissionMiddleware(permissions={"k8s.read", "prometheus.query"})

    # 方式2：从请求上下文动态获取（推荐）
    middleware = DynamicPermissionMiddleware()

    # 方式3：允许无权限模式（仅用于内部调用或测试）
    middleware = DynamicPermissionMiddleware(allow_no_permission_mode=True)

注意：
- 推荐使用方式2，配合 set_request_context(user_permissions=...) 使用
- 对于 deepagents 内置工具（如 write_todos, task 等），默认放行
- 如果请求上下文中没有 user_permissions，默认拒绝所有工具调用（安全优先）
"""

from typing import Set, Optional, Any, Awaitable, Callable

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ToolCallRequest,
)
from langchain_core.messages import ToolMessage

from app.tools.registry import get_tool_registry
from app.utils.logger import get_logger, get_request_context

logger = get_logger(__name__)


# deepagents 内置工具列表（这些工具不需要权限检查）
BUILTIN_TOOLS = {
    # DeepAgents 内置工具
    "write_todos",
    "task",  # subagent 委派
    "read_file",
    "write_file",
    "edit_file",
    "ls",
    "glob",
    "grep",
    # LangChain 内置工具
    "human",
    "ask_human",
}


class DynamicPermissionMiddleware(AgentMiddleware):
    """
    动态权限中间件

    在工具调用前检查用户是否有权限执行该工具。
    支持两种方式获取权限：
    1. 初始化时传入 permissions 参数（静态）
    2. 从请求上下文（get_request_context）动态获取（推荐）

    安全策略：
    - 默认情况下，如果上下文中没有 user_permissions，拒绝所有工具调用
    - 只有显式设置 allow_no_permission_mode=True 时才允许无权限模式

    Attributes:
        _static_permissions: 静态传入的权限集合
        _allow_no_permission_mode: 是否允许无权限模式
        user_id: 用户 ID（用于日志记录）
    """

    @property
    def name(self) -> str:
        return "DynamicPermissionMiddleware"

    def __init__(
        self,
        permissions: Set[str] = None,  # type: ignore[assignment]
        user_id: Optional[int] = None,
        allow_no_permission_mode: bool = False,
    ):
        """
        初始化权限中间件

        Args:
            permissions: 用户权限集合（可选，不传则从请求上下文获取）
            user_id: 用户 ID（可选，用于日志）
            allow_no_permission_mode: 是否允许无权限模式（默认 False，安全优先）
        """
        self._static_permissions = permissions
        self._allow_no_permission_mode = allow_no_permission_mode
        self.user_id = user_id

        # 获取工具注册表
        self._registry = get_tool_registry()

        ctx = get_request_context()
        session_id = ctx.get('session_id', 'no-sess')
        logger.info(
            f"🔐 [{session_id}] DynamicPermissionMiddleware 已初始化 | "
            f"user_id={user_id} | 静态权限={permissions is not None} | "
            f"允许无权限模式={allow_no_permission_mode}"
        )

    def _get_permissions(self) -> Optional[Set[str]]:
        """
        获取当前有效的权限集合

        Returns:
            - 权限集合（非空）：用户有这些权限
            - 空集合 set()：用户无权限，拒绝所有工具
            - None：无权限系统，允许所有工具（仅当 allow_no_permission_mode=True）
        """
        # 优先使用静态传入的权限
        if self._static_permissions is not None:
            return self._static_permissions

        # 从请求上下文获取权限
        ctx = get_request_context()
        permissions = ctx.get('user_permissions')

        if permissions is not None:
            # 用户权限已设置（可能是空集合）
            return set(permissions) if not isinstance(permissions, set) else permissions

        # 权限未设置
        if self._allow_no_permission_mode:
            # 允许无权限模式，放行所有工具
            return None

        # 安全优先：权限未设置时返回空集合，拒绝所有工具
        ctx_user_id = ctx.get('user_id')
        logger.warning(
            f"⚠️ 权限未设置且不允许无权限模式 | "
            f"middleware_user_id={self.user_id} | context_user_id={ctx_user_id}"
        )
        return set()  # 返回空集合，拒绝所有工具调用

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage]],  # type: ignore[override]
    ) -> ToolMessage:
        """
        在工具调用前拦截，检查权限

        Args:
            request: 工具调用请求
            handler: 下一个处理器

        Returns:
            工具调用结果或权限错误
        """
        tool_call = request.tool_call
        tool_name = tool_call.get("name", "unknown")
        tool_args = tool_call.get("args", {})
        tool_call_id = tool_call.get("id", "")

        ctx = get_request_context()
        session_id = ctx.get('session_id', 'no-sess')

        # 1. 内置工具默认放行
        if tool_name in BUILTIN_TOOLS:
            logger.debug(f"🔓 [{session_id}] 内置工具放行: {tool_name}")
            return await handler(request)

        # 2. 获取当前权限
        permissions = self._get_permissions()

        if permissions is None:
            # 没有权限限制，放行
            logger.debug(f"🔓 [{session_id}] 无权限限制，放行: {tool_name}")
            return await handler(request)

        # 3. 从 ToolRegistry 获取工具元数据
        tool_class = self._registry.get_tool(tool_name)

        if tool_class is None:
            # 工具不在注册表中，可能是动态创建的或外部工具
            # 默认放行，但记录警告
            logger.warning(f"⚠️ [{session_id}] 工具 '{tool_name}' 未在注册表中，默认放行")
            return await handler(request)

        metadata = tool_class.get_metadata()
        if metadata is None:
            # 没有元数据，默认放行
            logger.debug(f"🔓 [{session_id}] 工具 '{tool_name}' 无元数据，默认放行")
            return await handler(request)

        # 4. 获取工具所需的权限
        required_permissions = set(metadata.permissions)

        if not required_permissions:
            # 工具没有声明权限要求，根据 group 判断
            if metadata.group:
                required_permissions = {metadata.group}
            else:
                # 无 group 也无 permissions，默认放行
                logger.debug(f"🔓 [{session_id}] 工具 '{tool_name}' 无权限要求，默认放行")
                return await handler(request)

        # 5. 检查用户是否有所需权限
        has_permission = bool(required_permissions & permissions)

        if not has_permission:
            # 权限不足
            missing_perms = required_permissions - permissions
            logger.warning(
                f"🚫 [{session_id}] 权限拒绝 | "
                f"user_id={self.user_id} | tool={tool_name} | "
                f"需要权限={required_permissions} | 缺少={missing_perms}"
            )

            # 返回权限错误
            error_msg = (
                f"权限不足：无法执行工具 '{tool_name}'。"
                f"需要以下权限之一：{', '.join(required_permissions)}"
            )

            return ToolMessage(
                content=error_msg,
                tool_call_id=tool_call_id,
                status="error",
            )

        # 6. 有权限，放行
        logger.debug(
            f"✅ [{session_id}] 权限检查通过 | "
            f"tool={tool_name} | 权限={required_permissions & permissions}"
        )

        return await handler(request)


__all__ = ["DynamicPermissionMiddleware", "BUILTIN_TOOLS"]
