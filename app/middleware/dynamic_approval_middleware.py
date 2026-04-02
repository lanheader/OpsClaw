# app/middleware/dynamic_approval_middleware.py
"""
动态审批中间件

职责：
- 在模型生成后，检查 AI 消息中的工具调用
- 动态查询数据库，判断该工具是否需要审批
- 需要审批时，使用 LangGraph 的 interrupt 机制暂停执行
- 支持按角色配置不同的审批策略

使用方式：
    middleware = DynamicApprovalMiddleware(user_id=1, db_session=db)

注意：
- 此中间件需要在每次请求时创建新实例（携带当前用户 ID）
- 复用 app/services/approval_config_service.py 的逻辑
- 对于 deepagents 内置工具（如 write_todos, task 等），默认跳过审批检查
"""

from typing import Set, Optional, Any, Dict, List

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
)
from langchain_core.messages import AIMessage, ToolCall, ToolMessage
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from sqlalchemy.orm import Session

from app.services.approval_config_service import ApprovalConfigService
from app.models.database import SessionLocal
from app.models.role import Role
from app.models.user_role import UserRole
from app.utils.logger import get_logger, get_request_context

logger = get_logger(__name__)


# deepagents 内置工具列表（这些工具不需要审批检查）
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


class DynamicApprovalMiddleware(AgentMiddleware):
    """
    动态审批中间件

    在模型生成后检查工具调用是否需要审批。
    支持两种方式获取用户信息：
    1. 初始化时传入 user_id 参数（静态）
    2. 从请求上下文（get_request_context）动态获取（推荐）

    Attributes:
        _static_user_id: 静态传入的用户 ID
        tools_need_approval: 需要审批的工具名称集合（按用户缓存）
    """

    @property
    def name(self) -> str:
        return "DynamicApprovalMiddleware"

    def __init__(
        self,
        user_id: Optional[int] = None,
        db: Optional[Session] = None,
    ):
        """
        初始化审批中间件

        Args:
            user_id: 当前用户 ID（可选，不传则从请求上下文获取）
            db: 数据库会话（可选，如果不提供会创建新的）
        """
        self._static_user_id = user_id
        self._external_db = db is not None
        # 按用户 ID 缓存审批配置
        self._approval_cache: Dict[int, Set[str]] = {}

        ctx = get_request_context()
        session_id = ctx.get('session_id', 'no-sess')
        logger.info(
            f"🔒 [{session_id}] DynamicApprovalMiddleware 已初始化 | "
            f"static_user_id={user_id}"
        )

    def _get_user_id(self) -> Optional[int]:
        """获取当前有效的用户 ID"""
        if self._static_user_id is not None:
            return self._static_user_id

        # 从请求上下文获取
        ctx = get_request_context()
        return ctx.get('user_id')

    def _get_tools_need_approval(self, user_id: Optional[int]) -> Set[str]:
        """获取需要审批的工具集合（带缓存）"""

        # 即使 user_id 为 None 也加载审批配置（安全优先原则）
        # ContextVar 可能在子 task 中丢失，不能因此跳过审批

        # 检查缓存
        cache_key = user_id if user_id is not None else "__all__"
        if cache_key in self._approval_cache:
            return self._approval_cache[cache_key]

        # 从数据库加载
        db = SessionLocal()
        try:
            tools = self._load_approval_config(user_id, db)
            self._approval_cache[user_id] = tools
            return tools
        finally:
            db.close()

    def _load_approval_config(
        self,
        user_id: Optional[int],
        db: Optional[Session],
    ) -> Set[str]:
        """
        从数据库加载审批配置

        Args:
            user_id: 用户 ID
            db: 数据库会话

        Returns:
            需要审批的工具名称集合
        """
        should_close_db = False
        if db is None:
            db = SessionLocal()
            should_close_db = True

        try:
            # 获取用户角色
            user_role = self._get_user_role(user_id, db)

            # 从审批配置获取需要审批的工具
            tools_need_approval = ApprovalConfigService.get_tools_require_approval(
                db, user_role=user_role
            )

            logger.info(
                f"📋 从数据库加载审批配置: user_role={user_role}, "
                f"需审批工具数={len(tools_need_approval)}"
            )

            # 写入缓存
            self._approval_cache[cache_key] = tools_need_approval
            return tools_need_approval

        except Exception as e:
            logger.warning(f"⚠️ 加载审批配置失败: {e}，安全起见拦截所有高危险工具")
            # 加载失败时默认拦截所有已知的危险工具
            return {
                "force_delete_pod", "delete_pod", "delete_deployment",
                "delete_service", "delete_config_map", "delete_secret",
                "restart_deployment", "scale_deployment", "update_deployment_image",
            }

        finally:
            if should_close_db:
                db.close()

    def _get_user_role(self, user_id: Optional[int], db: Session) -> Optional[str]:
        """
        获取用户角色

        Args:
            user_id: 用户 ID
            db: 数据库会话

        Returns:
            用户角色名称，如果不存在则返回 None
        """
        if user_id is None:
            return None

        user_roles = (
            db.query(Role.name)
            .join(UserRole, Role.id == UserRole.role_id)
            .filter(UserRole.user_id == user_id)
            .all()
        )

        if user_roles:
            role_name = user_roles[0][0]
            logger.debug(f"🔐 获取到用户角色: {role_name}")
            return role_name

        return None

    async def aafter_model(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> Optional[Dict[str, Any]]:
        """
        在模型生成后检查工具调用，触发审批中断

        这是实现审批逻辑的核心方法。在 AI 模型生成消息后，
        检查其中的工具调用是否需要审批。

        Args:
            state: 当前 Agent 状态
            runtime: 运行时上下文

        Returns:
            状态更新字典，或 None（不需要更新）
        """
        messages = state.get("messages", [])
        if not messages:
            return None

        # 获取最后一条 AI 消息
        last_ai_msg = None
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                last_ai_msg = msg
                break

        if not last_ai_msg or not last_ai_msg.tool_calls:
            return None

        # 获取当前用户 ID 和审批配置
        user_id = self._get_user_id()
        tools_need_approval = self._get_tools_need_approval(user_id)

        # 收集需要审批的工具调用
        action_requests: List[Dict[str, Any]] = []
        review_configs: List[Dict[str, Any]] = []
        interrupt_indices: List[int] = []

        ctx = get_request_context()
        session_id = ctx.get('session_id', 'no-sess')

        for idx, tool_call in enumerate(last_ai_msg.tool_calls):
            tool_name = tool_call.get("name", "unknown")
            tool_args = tool_call.get("args", {})

            # 跳过内置工具
            if tool_name in BUILTIN_TOOLS:
                continue

            # 检查是否需要审批
            if tool_name in tools_need_approval:
                # 创建 ActionRequest
                action_request = {
                    "name": tool_name,
                    "args": tool_args,
                    "description": f"工具 {tool_name} 需要审批后执行",
                }
                action_requests.append(action_request)

                # 创建 ReviewConfig（允许批准或拒绝）
                review_config = {
                    "action_name": tool_name,
                    "allowed_decisions": ["approve", "reject"],
                }
                review_configs.append(review_config)
                interrupt_indices.append(idx)

                ctx = get_request_context()
                session_id = ctx.get('session_id', 'no-sess')
                logger.info(
                    f"🔒 [{session_id}] 工具需要审批: {tool_name} | "
                    f"args={tool_args}"
                )

        # 如果没有需要审批的工具调用，直接返回
        if not action_requests:
            return None

        # 创建 HITLRequest 并触发中断
        hitl_request = {
            "action_requests": action_requests,
            "review_configs": review_configs,
        }

        ctx = get_request_context()
        session_id = ctx.get('session_id', 'no-sess')
        logger.info(
            f"🛑 [{session_id}] 触发审批中断: {len(action_requests)} 个工具需要审批"
        )

        # 调用 interrupt 暂停执行
        decisions = interrupt(hitl_request)["decisions"]

        # 处理用户决策
        return self._process_decisions(
            decisions, last_ai_msg, interrupt_indices, session_id
        )

    def _process_decisions(
        self,
        decisions: List[Dict[str, Any]],
        original_ai_msg: AIMessage,
        interrupt_indices: List[int],
        session_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        处理用户的审批决策

        Args:
            decisions: 用户决策列表
            original_ai_msg: 原始 AI 消息
            interrupt_indices: 被中断的工具调用索引
            session_id: 会话 ID

        Returns:
            状态更新字典
        """
        if len(decisions) != len(interrupt_indices):
            logger.warning(
                f"⚠️ [{session_id}] 决策数量不匹配: "
                f"decisions={len(decisions)}, interrupts={len(interrupt_indices)}"
            )
            return None

        revised_tool_calls: List[ToolCall] = []
        artificial_tool_messages: List[ToolMessage] = []

        decision_idx = 0
        for idx, tool_call in enumerate(original_ai_msg.tool_calls):
            tool_name = tool_call.get("name", "unknown")
            tool_call_id = tool_call.get("id", "")
            tool_args = tool_call.get("args", {})

            if idx in interrupt_indices:
                # 这是需要审批的工具调用
                decision = decisions[decision_idx]
                decision_type = decision.get("type", "reject")
                decision_idx += 1

                if decision_type == "approve":
                    # 用户批准，保留原始工具调用
                    revised_tool_calls.append(tool_call)
                    logger.info(f"✅ [{session_id}] 工具已批准: {tool_name}")

                elif decision_type == "reject":
                    # 用户拒绝，添加拒绝消息
                    reject_msg = decision.get("message", "用户拒绝了此操作")
                    artificial_tool_messages.append(
                        ToolMessage(
                            content=f"❌ 操作被拒绝: {reject_msg}",
                            tool_call_id=tool_call_id,
                            status="error",
                        )
                    )
                    logger.info(f"🚫 [{session_id}] 工具已拒绝: {tool_name}")

                elif decision_type == "edit":
                    # 用户编辑了参数
                    edited_action = decision.get("edited_action", {})
                    revised_call = {
                        "name": edited_action.get("name", tool_name),
                        "args": edited_action.get("args", tool_args),
                        "id": tool_call_id,
                        "type": "tool_call",
                    }
                    revised_tool_calls.append(revised_call)
                    logger.info(
                        f"✏️ [{session_id}] 工具参数已编辑: {tool_name} -> "
                        f"{edited_action.get('args', tool_args)}"
                    )
            else:
                # 不需要审批的工具调用，保留原始
                revised_tool_calls.append(tool_call)

        # 更新 AI 消息的工具调用列表
        original_ai_msg.tool_calls = revised_tool_calls

        # 返回状态更新
        result = {"messages": [original_ai_msg]}
        if artificial_tool_messages:
            result["messages"].extend(artificial_tool_messages)

        return result


__all__ = ["DynamicApprovalMiddleware", "BUILTIN_TOOLS"]
