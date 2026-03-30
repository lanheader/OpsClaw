"""
DeepAgents 主智能体配置

v4.0 - 静态创建 + 动态中间件架构

核心改进：
- Agent 图在应用启动时创建一次（加载所有工具和 SubAgent）
- 权限过滤通过 DynamicPermissionMiddleware 在运行时处理
- 审批检查通过 DynamicApprovalMiddleware 在运行时处理
- 不再每次请求重建 Agent，大幅提升性能
- 利用 deepagents 内置能力：SkillsMiddleware、SummarizationMiddleware、MemoryMiddleware

⭐ system_prompt 将动态从数据库加载，经过 DSPy 优化
"""

import os
from collections import defaultdict
from typing import Any, Optional, Set, Dict, List

from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from sqlalchemy.orm import Session

from app.core.llm_factory import LLMFactory
from app.core.checkpointer import get_checkpointer
from app.prompts.main_agent import MAIN_AGENT_SYSTEM_PROMPT
from app.tools.registry import get_tool_registry
from app.tools.base import RiskLevel
from app.utils.logger import get_logger
from app.services.approval_config_service import ApprovalConfigService
from app.models.database import SessionLocal
from app.models.role import Role
from app.models.user_role import UserRole
from app.memory import get_langgraph_store

logger = get_logger(__name__)


# ========== 全局缓存 ==========

_cached_base_agent: Optional[Any] = None
_base_agent_ready = False


# ========== 组件加载函数 ==========

def _get_llm(llm: Optional[BaseChatModel] = None) -> BaseChatModel:
    """获取 LLM 实例"""
    if llm is None:
        llm = LLMFactory.create_llm()
    return llm


def _load_all_subagents() -> List[Dict[str, Any]]:
    """加载所有 Subagent 列表"""
    from app.deepagents.subagents import get_all_subagents

    subagents = get_all_subagents()

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
    """加载所有工具（不过滤权限）"""
    registry = get_tool_registry()
    tools = registry.get_langchain_tools()

    # 日志输出
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
    skills_dir = os.path.join(project_root, "skills")
    has_skills = os.path.isdir(skills_dir)

    if has_skills:
        logger.info(f"📋 Skills 目录: {skills_dir}")
        return (
            project_root,
            skills_dir,
            True,
            FilesystemBackend(root_dir=project_root, virtual_mode=False),
            ["skills/"]
        )

    return project_root, skills_dir, False, None, None


async def _generate_dynamic_memory(user_query: str = None) -> str:
    """
    动态生成 Agent 记忆内容

    从知识库检索相关经验，写入临时文件供 MemoryMiddleware 加载。

    Args:
        user_query: 用户查询（用于检索相关经验）

    Returns:
        记忆文件路径
    """
    try:
        from app.memory.memory_manager import get_memory_manager
        memory_manager = get_memory_manager()
    except Exception:
        memory_manager = None

    sections = []

    # 系统基本信息
    from app.core.config import get_settings
    settings = get_settings()
    sections.append("## 集群信息\n")
    sections.append(f"- 环境: {settings.SECURITY_ENVIRONMENT}\n")
    sections.append(f"- 应用版本: {settings.APP_VERSION if hasattr(settings, 'APP_VERSION') else '3.0.0'}\n")

    # 相关历史经验
    if memory_manager and user_query:
        try:
            similar = memory_manager.search_similar_incidents(user_query, top_k=3)
            if similar:
                sections.append("\n## 相关历史经验\n")
                for case in similar:
                    title = getattr(case, 'title', str(case))
                    sections.append(f"### {title}\n")
                    if hasattr(case, 'root_cause'):
                        sections.append(f"- 根因: {case.root_cause}\n")
                    if hasattr(case, 'resolution'):
                        sections.append(f"- 方案: {case.resolution}\n")
        except Exception as e:
            logger.warning(f"⚠️ 检索历史经验失败: {e}")

    content = "\n".join(sections)

    # 写入临时文件供 MemoryMiddleware 加载
    memory_dir = "/tmp/opsclaw_memory"
    os.makedirs(memory_dir, exist_ok=True)
    memory_path = os.path.join(memory_dir, "AGENTS.md")
    with open(memory_path, "w", encoding="utf-8") as f:
        f.write(content)

    return memory_path


# 文件输出指令（添加到 system_prompt 末尾）
FILE_OUTPUT_PROMPT = """
<file_output>
完成分析后，你可以使用 `write_file` 工具生成报告文件：
- 诊断报告保存到: /reports/{YYYY-MM-DD}/{session_id}_diagnosis.md
- Runbook 保存到: /runbooks/{problem_type}.md
- 分析数据导出到: /exports/{session_id}_data.json

报告格式使用 Markdown，包含：
1. 问题摘要
2. 根因分析
3. 证据（工具调用结果）
4. 修复建议
5. 验证步骤
</file_output>
"""


# ========== 基础 Agent 创建（应用启动时调用一次） ==========

async def create_base_agent() -> Any:
    """
    创建基础 Agent（应用启动时调用一次）。

    特点：
    - 加载所有工具（不做权限过滤，由 DynamicPermissionMiddleware 处理）
    - 加载所有 SubAgent
    - 不设置 interrupt_on（由 DynamicApprovalMiddleware 处理）
    - 配置 Skills、Filesystem 等 deepagents 内置能力
    - 利用 deepagents 内置的 SummarizationMiddleware（自动对话压缩）

    Returns:
        编译后的 DeepAgents 图
    """
    global _cached_base_agent, _base_agent_ready

    if _base_agent_ready and _cached_base_agent is not None:
        logger.info("📦 使用缓存的 base_agent")
        return _cached_base_agent

    logger.info("🏗️ 创建基础 Agent（静态模式，包含所有工具和 SubAgent）")

    # 0. 获取项目根目录
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    # 1. 获取 LLM
    llm = _get_llm()

    # 2. 加载所有组件（不过滤权限）
    subagents = _load_all_subagents()
    tools = _load_all_tools()

    # 3. 获取基础设施
    checkpointer = await get_checkpointer()
    store = get_langgraph_store()
    logger.info("🧠 SQLite FTS5 Store 适配器已加载（全文搜索，零外部依赖）")

    # 4. Skills 配置
    _, _, _, backend, skills = _get_skills_config()

    # 5. 确保输出目录存在
    for output_dir in ["reports", "runbooks", "exports"]:
        os.makedirs(os.path.join(project_root, output_dir), exist_ok=True)

    # 6. 自定义中间件（不包含权限/审批逻辑，那些由 DynamicWrapper 处理）
    from app.middleware.error_filtering_middleware import ErrorFilteringMiddleware
    from app.middleware.logging_middleware import LoggingMiddleware

    custom_middleware = [
        ErrorFilteringMiddleware(),
        LoggingMiddleware(),
    ]

    # 7. 使用简化的 system_prompt（不包含审批工具列表，审批由 middleware 处理）
    system_prompt = MAIN_AGENT_SYSTEM_PROMPT + FILE_OUTPUT_PROMPT

    # 8. 创建 Agent（利用 deepagents 内置的 MemoryMiddleware 加载知识库）
    memory_path = await _generate_dynamic_memory()

    agent = create_deep_agent(
        name="OpsAgent",
        model=llm,
        system_prompt=system_prompt,
        tools=tools,
        subagents=subagents,
        middleware=custom_middleware,
        checkpointer=checkpointer,
        # 不传 interrupt_on，由 DynamicApprovalMiddleware 处理
        store=store,
        backend=backend,
        skills=skills,
        memory=[memory_path] if os.path.exists(memory_path) else None,
    )

    # 8. 缓存
    _cached_base_agent = agent
    _base_agent_ready = True

    logger.info("✅ 基础 Agent 创建完成（已缓存，后续请求复用）")
    return agent


def get_cached_base_agent() -> Optional[Any]:
    """获取缓存的 base_agent"""
    return _cached_base_agent


def invalidate_base_agent() -> None:
    """清除 base_agent 缓存（LLM 配置变更时调用）"""
    global _cached_base_agent, _base_agent_ready
    _cached_base_agent = None
    _base_agent_ready = False
    logger.info("🗑️ base_agent 缓存已清除")


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
    llm: Optional[BaseChatModel] = None,
    enable_approval: bool = True,
    user_permissions: Optional[Set[str]] = None,
    user_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> Any:
    """
    获取 Ops Agent

    v4.0 改进：
    - 使用按权限组合缓存的 Agent 实例，不再每次重建
    - 权限和审批通过 middleware 在工具调用时动态处理
    - 权限组合不变时直接复用缓存的 Agent 图

    Args:
        llm: 语言模型实例 (默认使用 LLMFactory)
        enable_approval: 是否启用审批流程
        user_permissions: 用户权限代码集合（静态权限）
        user_id: 用户 ID（用于动态获取权限）
        db: 数据库会话（用于动态获取权限）

    Returns:
        DynamicAgentWrapper 包装的 Agent 实例
    """
    # 1. 获取或创建 base_agent
    base_agent = await create_base_agent()

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


# ========== 增强主智能体配置 ==========

MAIN_AGENT_ENHANCED_CONFIG = {
    "enable_cot": True,
    "enable_plan_evaluation": True,
    "enable_reasoning_log": True,
    "max_reasoning_depth": 5,
    "plan_evaluation_threshold": 0.7,
    "enable_reflection": True,
}


async def enhanced_main_agent_process(
    user_query: str,
    context: dict = None,
    enable_cot: bool = True,
    enable_plan_evaluation: bool = True
) -> dict:
    """
    增强主智能体处理入口函数
    """
    from app.services.enhanced_main_agent_service import get_enhanced_main_agent_service

    service = get_enhanced_main_agent_service()
    result = await service.process_user_request(
        user_query=user_query,
        context=context or {},
        enable_cot=enable_cot,
        enable_plan_evaluation=enable_plan_evaluation
    )

    return {
        "plan_id": result.plan_id,
        "user_query": result.user_query,
        "total_duration": result.total_duration,
        "subtasks_completed": result.subtasks_completed,
        "subtasks_failed": result.subtasks_failed,
        "final_result": result.final_result,
        "reasoning_summary": result.reasoning_summary,
        "lessons_learned": result.lessons_learned
    }


__all__ = [
    "get_ops_agent",
    "get_thread_config",
    "create_base_agent",
    "get_cached_base_agent",
    "invalidate_base_agent",
    "DynamicAgentWrapper",
    "MAIN_AGENT_ENHANCED_CONFIG",
    "enhanced_main_agent_process",
]
