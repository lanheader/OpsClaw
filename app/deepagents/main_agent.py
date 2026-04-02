import os
from collections import defaultdict
from typing import Any, Optional, Set, Dict, List

from deepagents import create_deep_agent, SubAgent
from deepagents.backends.filesystem import FilesystemBackend
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from sqlalchemy.orm import Session

from app.middleware.error_filtering_middleware import ErrorFilteringMiddleware
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.dynamic_permission_middleware import DynamicPermissionMiddleware
from app.middleware.dynamic_approval_middleware import DynamicApprovalMiddleware
from langchain.agents.middleware.summarization import SummarizationMiddleware
from app.core.llm_factory import LLMFactory
from app.core.checkpointer import get_checkpointer
from app.services.unified_prompt_optimizer import get_prompt_optimizer
from app.tools.registry import get_tool_registry
from app.utils.logger import get_logger
from app.memory import get_langgraph_store
from app.core.constants import MiddlewareConfig

logger = get_logger(__name__)


# ========== 组件加载函数 ==========

def _get_llm(llm: Optional[BaseChatModel] = None) -> BaseChatModel:
    """获取 LLM 实例"""
    if llm is None:
        llm = LLMFactory.create_llm()
    return llm


def _load_all_subagents(db: Optional[Session] = None) -> List[SubAgent]:
    """加载所有 Subagent 列表（工具按集成开关动态过滤）"""
    from app.deepagents.subagents import get_all_subagents

    subagents = get_all_subagents(db=db)

    # 日志输出
    logger.info("=" * 60)
    logger.info("🤖 主智能体可用 Subagent 列表:")
    for subagent in subagents:
        name = subagent.get('name', 'unknown')
        desc = subagent.get('description', 'No description')
        tool_count = len(subagent.get('tools', []))
        logger.info(f"  - {name}: {desc}")
        logger.info(f"    工具数量: {tool_count}")
    logger.info(f"📊 总计: {len(subagents)} 个 Subagent")
    logger.info("=" * 60)

    return subagents


def _load_all_tools() -> List[Any]:
    """加载所有工具（过滤未启用的集成）"""
    registry = get_tool_registry()
    try:
        from app.models.database import SessionLocal
        db = SessionLocal()
        tools = registry.get_langchain_tools(db=db)
        db.close()
    except Exception:
        tools = registry.get_langchain_tools()

    # 日志输出
    _log_tools_info(tools)

    return tools


def _load_tools_for_user(user_id: Optional[int] = None, db: Optional[Session] = None) -> List[Any]:
    """按用户权限动态加载工具"""
    registry = get_tool_registry()
    try:
        if user_id is not None and db is not None:
            tools = registry.get_langchain_tools(user_id=user_id, db=db)
            logger.info(f"🔧 按用户权限加载工具: user_id={user_id}, 工具数={len(tools)}")
        else:
            tools = _load_all_tools()
    except Exception:
        tools = _load_all_tools()

    _log_tools_info(tools)
    return tools


def _log_tools_info(tools: List[Any]) -> None:
    """输出工具分组信息"""
    logger.info("=" * 60)
    logger.info("🛠️  主智能体可用工具列表:")
    logger.info("=" * 60)

    tool_groups = defaultdict(list)
    registry = get_tool_registry()

    for tool in tools:
        tool_name = getattr(tool, 'name', 'unknown')
        tool_class = registry.get_tool(tool_name)

        if tool_class:
            metadata = tool_class.get_metadata()
            if metadata:
                group_name = metadata.group.replace('.', ' ').title()
                tool_groups[group_name].append(tool_name)

    for group, tool_names in sorted(tool_groups.items()):
        logger.info(f"  [{group}] {len(tool_names)} 个:")
        for name in sorted(tool_names):
            logger.info(f"    - {name}")

    logger.info(f"📊 总计: {len(tools)} 个工具")
    logger.info("=" * 60)


def _get_skills_config() -> tuple:
    """获取 Skills 配置"""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    skills_dir = os.path.join(project_root, "workspace", "skills")
    has_skills = os.path.isdir(skills_dir)

    if has_skills:
        logger.info(f"📋 Skills 目录: {skills_dir}")
        return (
            project_root,
            skills_dir,
            True,
            FilesystemBackend(root_dir=project_root, virtual_mode=False),
            ["workspace/skills/"]
        )

    return project_root, skills_dir, False, None, None


# 文件输出指令（添加到 system_prompt 末尾）
FILE_OUTPUT_PROMPT = """
<language_rule>
- 你必须始终使用中文（简体中文）回复用户
- 所有分析报告、诊断结果、修复建议都必须使用中文
- 工具调用参数保持英文（如 namespace、label 等），但回复内容的描述必须用中文
- 专业术语可以保留英文原文，但需附中文解释（如 CPU 使用率、OOM 等）
</language_rule>

<file_output>
完成分析后，你可以使用 `write_file` 工具生成报告文件：
- 诊断报告保存到: /workspace/reports/{YYYY-MM-DD}/{session_id}_diagnosis.md
- Runbook 保存到: /workspace/runbooks/{problem_type}.md
- 分析数据导出到: /workspace/exports/{session_id}_data.json

报告格式使用 Markdown，包含：
1. 问题摘要
2. 根因分析
3. 证据（工具调用结果）
4. 修复建议
5. 验证步骤
</file_output>
"""


# ========== 基础 Agent 创建（应用启动时调用一次） ==========

async def create_base_agent(user_id: Optional[int] = None, db: Optional[Session] = None) -> Any:
    """
    懒加载创建 Agent，每次都新建（不缓存）。
    创建前根据 user_id+db 查用户角色，动态生成 interrupt_on。

    Args:
        user_id: 用户 ID
        db: 数据库会话
    """
    logger.info("🏗️ 创建 Agent（懒加载）")

    # 0. 获取项目根目录
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    # 1. 获取 LLM
    llm = _get_llm()

    # 2. 按用户权限加载工具（不过滤则加载全部）
    subagents = _load_all_subagents(db)
    tools = _load_tools_for_user(user_id, db)

    # 3. 获取基础设施
    checkpointer = await get_checkpointer()
    store = get_langgraph_store()
    logger.info("🧠 SQLite FTS5 Store 适配器已加载（全文搜索，零外部依赖）")

    # 4. Skills 配置
    _, _, _, backend, skills = _get_skills_config()

    # 5. 确保输出目录存在
    for output_dir in ["reports", "runbooks", "exports"]:
        os.makedirs(os.path.join(project_root, output_dir), exist_ok=True)

    # 获取需要审批的工具（从已加载的工具列表中筛选）
    interrupt_on = {}
    tool_names = {t.name for t in tools}
    try:
        from app.services.approval_config_service import ApprovalConfigService

        # 查用户角色
        user_role = None
        if user_id is not None and db is not None:
            try:
                from app.models.user_role import UserRole
                from app.models.role import Role
                roles = (
                    db.query(Role.name)
                    .join(UserRole, Role.id == UserRole.role_id)
                    .filter(UserRole.user_id == user_id)
                    .all()
                )
                user_role = roles[0][0] if roles else None
            except Exception as e:
                logger.warning(f"获取用户角色失败: {e}")

        # db 为 None 时用临时连接
        _db = db
        _should_close = False
        if _db is None:
            from app.models.database import SessionLocal
            _db = SessionLocal()
            _should_close = True

        try:
            tools_need_approval = ApprovalConfigService.get_tools_require_approval(
                _db, user_role=user_role
            )
            # 关键：只对用户可用的工具中的需审批工具设置 interrupt_on
            for tool_name in tools_need_approval:
                if tool_name in tool_names:
                    interrupt_on[tool_name] = True
            logger.info(
                f"🔒 审批配置: user_id={user_id}, role={user_role}, "
                f"可用工具={len(tool_names)}, 需审批={list(interrupt_on.keys())}"
            )
        finally:
            if _should_close:
                _db.close()
    except Exception as e:
        logger.warning(f"⚠️ 加载审批配置失败: {e}，安全兜底拦截所有高风险工具")
        for t in [
            "force_delete_pod", "delete_pod", "delete_deployment",
            "delete_service", "delete_config_map", "delete_secret",
            "restart_deployment", "scale_deployment", "update_deployment_image",
        ]:
            interrupt_on[t] = True

    custom_middleware = [
        ErrorFilteringMiddleware(),
        LoggingMiddleware(),
        # 消息摘要中间件：防止 token 超长（使用 MiddlewareConfig 配置）
        SummarizationMiddleware(
            model=llm,  # 必填参数：用于生成摘要的 LLM
            trigger=("messages", MiddlewareConfig.COMPRESSION_THRESHOLD),  # 超过 30 条消息触发摘要
            keep=("messages", MiddlewareConfig.MAX_FULL_MESSAGES),  # 保留最近 20 条完整消息
        ),
        # 权限中间件：从请求上下文获取权限，检查工具调用权限
        DynamicPermissionMiddleware(),
        # 审批中间件：日志记录模式（实际拦截由 interrupt_on 保证）
        DynamicApprovalMiddleware(),
    ]
    logger.info("🔧 已加载中间件: 错误过滤、日志记录、消息摘要、权限检查、审批检查")

    # 7. 从数据库加载 system_prompt（优先数据库，降级到默认提示词）
    prompt_optimizer = get_prompt_optimizer()
    try:
        main_prompt = prompt_optimizer.get_prompt_for_agent("main-agent")
    except ValueError:
        # 如果数据库中没有，使用默认提示词
        main_prompt = """你是一个智能运维助手（OpsClaw），负责帮助用户诊断和解决 Kubernetes 集群问题。

## 核心能力
1. 集群状态查询和分析
2. 问题诊断和根因分析
3. 执行修复操作（需要审批）
4. 生成诊断报告

## 工作流程
1. 理解用户问题
2. 收集相关数据
3. 分析问题原因
4. 提供解决方案
5. 执行修复（如需要）

## 注意事项
- 执行危险操作前需要用户确认
- 提供清晰的问题分析报告
- 给出可操作的解决方案"""

    system_prompt = main_prompt + FILE_OUTPUT_PROMPT

    # 8. 创建 Agent（记忆注入由 agent_chat_service._inject_memory 处理）
    agent = create_deep_agent(
        name="OpsAgent",
        model=llm,
        system_prompt=system_prompt,
        tools=tools,
        subagents=subagents,
        middleware=custom_middleware,
        checkpointer=checkpointer,
        store=store,
        backend=backend,
        skills=skills,
        interrupt_on=interrupt_on if interrupt_on else None,
    )

    logger.info("✅ Agent 创建完成")
    return agent



# ========== 动态 Agent 包装器 ==========

class DynamicAgentWrapper:
    """
    Agent 动态包装器。

    将 base_agent 和动态 middleware（权限 + 审批）组合，
    在每次工具调用时检查权限和审批。

    工作原理：
    - ainvoke/astream 直接调用 base_agent
    - 通过修改 state 注入权限和审批信息
    - DynamicPermissionMiddleware 和 DynamicApprovalMiddleware
      在 base_agent 创建时已通过 create_deep_agent 的 middleware 注入

    注意：由于 deepagents 不支持运行时动态注入 middleware，
    当前实现采用"每次请求创建 Agent 实例 + 缓存"的策略。
    但相比之前，优化了缓存策略：
    - SubAgent 列表全局缓存
    - 工具列表按权限组合缓存
    - 中间件按权限组合缓存
    - 只有权限组合变化时才重建 Agent
    """

    def __init__(
        self,
        agent: Any,
        user_permissions: Optional[Set[str]] = None,
    ):
        self._agent = agent
        self._user_permissions = user_permissions

    async def ainvoke(self, input_data: Any, config: Optional[dict] = None, **kwargs: Any) -> Any:
        """同步调用 base_agent"""
        result = await self._agent.ainvoke(input_data, config=config, **kwargs)
        return _ensure_final_report(result)

    async def astream(self, input_data: Any, config: Optional[dict] = None, **kwargs: Any):
        """
        流式调用 base_agent，确保最后一个事件包含 final_report
        """
        last_event = None
        last_node_name = None

        async for event in self._agent.astream(input_data, config=config, **kwargs):
            # 处理 __interrupt__ 事件（审批中断）
            if isinstance(event, dict) and "__interrupt__" in event:
                yield event
                last_event = None
                continue

            # 处理自定义 complete 事件
            if (
                isinstance(event, dict)
                and event.get("type") == "complete"
                and isinstance(event.get("state"), dict)
            ):
                yield {
                    **event,
                    "state": _ensure_final_report(event["state"]),
                }
                last_event = None
                continue

            # 记录最后一个节点事件
            if isinstance(event, dict):
                for key in event.keys():
                    if not key.startswith("__"):
                        last_event = event
                        last_node_name = key
                        break

            yield event

        # 流结束后，确保包含 final_report
        if last_event and last_node_name:
            node_state = last_event.get(last_node_name, {})
            if isinstance(node_state, dict) and "messages" in node_state:
                enriched_state = _ensure_final_report(node_state)
                if enriched_state.get("formatted_response") or enriched_state.get("final_report"):
                    from app.utils.logger import get_logger
                    _logger = get_logger(__name__)
                    _logger.info(f"📝 流结束后生成 final_report")
                    yield {
                        "type": "complete",
                        "state": enriched_state,
                        "node": last_node_name,
                    }

    def __getattr__(self, name: str) -> Any:
        """代理其他属性访问到 base_agent"""
        return getattr(self._agent, name)


def _ensure_final_report(state: dict) -> dict:
    """确保 state 中包含 final_report"""
    if not isinstance(state, dict):
        return state

    from app.utils.llm_helper import ensure_final_report_in_state
    return ensure_final_report_in_state(state)


# ========== 主入口函数（兼容接口） ==========

async def get_ops_agent(
    user_permissions: Optional[Set[str]] = None,
    user_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> Any:
    """
    获取 OpsClaw

    v4.0 改进：
    - 使用按权限组合缓存的 Agent 实例，不再每次重建
    - 权限和审批通过 middleware 在工具调用时动态处理
    - 权限组合不变时直接复用缓存的 Agent 图

    Args:
        user_permissions: 用户权限代码集合（静态权限）
        user_id: 用户 ID（用于动态获取权限）
        db: 数据库会话（用于动态获取权限）

    Returns:
        DynamicAgentWrapper 包装的 Agent 实例
    """
    # 1. 创建 agent（懒加载，根据用户角色动态生成 interrupt_on）
    _db = db
    _should_close_db = False
    if _db is None:
        from app.models.database import SessionLocal
        _db = SessionLocal()
        _should_close_db = True

    try:
        base_agent = await create_base_agent(user_id=user_id, db=_db)
    finally:
        if _should_close_db:
            _db.close()

    # 2. 获取用户权限（如果提供了 user_id 和 db）
    if user_id is not None and db is not None:
        registry = get_tool_registry()
        tools = registry.get_langchain_tools(user_id=user_id, db=db)
        permissions = {t.name for t in tools}
        logger.info(f"🔐 用户权限: user_id={user_id}, 工具数={len(tools)}")
    elif user_permissions is not None:
        permissions = user_permissions
        logger.info(f"🔐 静态权限: {len(user_permissions)} 个权限")
    else:
        permissions = None
        logger.info("✅ 未指定权限，使用全部工具")

    # 3. 返回包装器
    return DynamicAgentWrapper(
        agent=base_agent,
        user_permissions=permissions,
    )


def get_thread_config(session_id: str) -> dict:
    """
    获取会话配置（用于 astream/ainvoke 的 config 参数）

    Args:
        session_id: 会话 ID

    Returns:
        LangGraph config dict，thread_id = session_id，与 chat_sessions 表关联
    """
    return {"configurable": {"thread_id": session_id}}


__all__ = [
    "get_ops_agent",
    "get_thread_config",
    "create_base_agent",
    "DynamicAgentWrapper",
]
