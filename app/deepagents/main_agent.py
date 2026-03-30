"""
DeepAgents 主智能体配置

负责任务规划、子智能体委派、批准流程和智能路由

增强版（v3.3）：
- CoT (Chain of Thought): 显式推理链
- Plan-and-Solve: 详细任务规划
- Self-Reflection: 规划评估和调整
- 向量记忆: 长期记忆和知识库检索
- 记忆中间件: 自动增强上下文
- 组件缓存: Subagent/Middleware/Tools 缓存优化

⭐ system_prompt 将动态从数据库加载，经过 DSPy 优化
"""

import os
from collections import defaultdict
from typing import Any, Optional, Set, Dict, List

from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend
from langchain_core.language_models import BaseChatModel
from sqlalchemy.orm import Session

from app.core.llm_factory import LLMFactory
from app.core.checkpointer import get_checkpointer
from app.prompts.main_agent import MAIN_AGENT_SYSTEM_PROMPT
from app.deepagents.component_cache import ComponentCache
from app.tools.registry import get_tool_registry
from app.tools.base import RiskLevel
from app.utils.logger import get_logger
from app.services.approval_config_service import ApprovalConfigService
from app.models.database import SessionLocal
from app.models.role import Role
from app.models.user_role import UserRole
from app.memory import get_langgraph_store

logger = get_logger(__name__)


# ========== 组件加载函数 ==========

def _get_llm(llm: Optional[BaseChatModel] = None) -> BaseChatModel:
    """获取 LLM 实例"""
    if llm is None:
        llm = LLMFactory.create_llm()
    return llm


def _load_subagents() -> List[Dict[str, Any]]:
    """加载 Subagent 列表（带缓存）"""
    subagents = ComponentCache.get_subagents()

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


def _load_tools(
    user_id: Optional[int] = None,
    db: Optional[Session] = None,
    user_permissions: Optional[Set[str]] = None,
) -> List[Any]:
    """
    加载工具列表（带缓存，按权限过滤）

    优先级：
    1. 动态权限（user_id + db）
    2. 静态权限（user_permissions）
    3. 无权限过滤
    """
    if user_id is not None and db is not None:
        logger.info(f"🔐 使用动态权限过滤工具（user_id: {user_id}）")
        tools = ComponentCache.get_tools(user_id=user_id, db=db)
    elif user_permissions is not None:
        logger.info(f"🔐 使用静态权限过滤工具（权限: {', '.join(sorted(user_permissions))}）")
        tools = ComponentCache.get_tools(permissions=user_permissions)
    else:
        logger.info("✅ 未指定用户权限，加载所有工具")
        tools = ComponentCache.get_tools()

    logger.info(f"📊 加载工具数量: {len(tools)} 个")
    return tools


def _load_middleware() -> List[Any]:
    """加载中间件列表（带缓存）"""
    middleware = ComponentCache.get_middleware()
    logger.info(f"✅ 已加载 {len(middleware)} 个中间件")
    return middleware


# ========== 审批配置函数 ==========

def _get_user_role(user_id: Optional[int], db: Session) -> Optional[str]:
    """获取用户角色"""
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
        logger.info(f"🔐 获取到用户角色: {role_name} (共 {len(user_roles)} 个角色)")
        return role_name

    return None


def _get_tools_need_approval(
    enable_approval: bool,
    user_id: Optional[int] = None,
) -> Set[str]:
    """
    获取需要审批的工具列表

    优先从数据库获取审批配置，失败则回退到基于风险等级的判断。
    """
    if not enable_approval:
        return set()

    tools_need_approval = set()
    config_db = SessionLocal()

    try:
        # 获取用户角色
        user_role = _get_user_role(user_id, config_db)

        # 从审批配置获取需要审批的工具
        tools_need_approval = ApprovalConfigService.get_tools_require_approval(
            config_db, user_role=user_role
        )
        logger.info(f"🔒 从审批配置获取需要审批的工具: {len(tools_need_approval)} 个")

    except Exception as e:
        # 回退到基于风险等级的判断
        logger.warning(f"⚠️ 无法从数据库获取审批配置，使用风险等级判断: {e}")
        tools_need_approval = _get_high_risk_tools()

    finally:
        config_db.close()

    return tools_need_approval


def _get_high_risk_tools() -> Set[str]:
    """获取高风险工具列表（回退方案）"""
    registry = get_tool_registry()
    high_risk_tools = set()

    for tool_class in registry.list_tools():
        metadata = tool_class.get_metadata()
        if metadata and metadata.risk_level == RiskLevel.HIGH:
            high_risk_tools.add(metadata.name)

    logger.info(f"🔒 基于风险等级判断的高风险工具: {len(high_risk_tools)} 个")
    return high_risk_tools


# ========== 系统提示词构建 ==========

def _build_system_prompt(tools_need_approval: Set[str]) -> str:
    """
    构建系统提示词

    如果有需要审批的工具，在提示词中添加说明。
    """
    system_prompt = MAIN_AGENT_SYSTEM_PROMPT

    if tools_need_approval:
        approval_list = "\n".join([f"  - {tool}" for tool in sorted(tools_need_approval)])
        system_prompt += (
            f"\n\n⚠️ **注意：以下工具属于高风险操作**\n\n"
            f"{approval_list}\n\n"
            f"当你需要使用这些工具时，直接调用即可，系统会自动处理审批流程。"
        )

    return system_prompt


# ========== 日志输出函数 ==========

def _log_tools_info(tools: List[Any]) -> None:
    """输出工具分组信息"""
    logger.info("=" * 60)
    logger.info("🛠️  主智能体可用工具列表:")
    logger.info("=" * 60)

    # 按分组整理工具
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

    # 输出分组信息
    for group, tool_names in sorted(tool_groups.items()):
        logger.info(f"  [{group}] {len(tool_names)} 个:")
        for name in sorted(tool_names):
            logger.info(f"    - {name}")

    logger.info(f"📊 总计: {len(tools)} 个工具")
    logger.info("=" * 60)


# ========== Agent 创建函数 ==========

def _build_interrupt_on(tools_need_approval: Set[str]) -> Optional[Dict[str, bool]]:
    """构建 interrupt_on 配置"""
    if tools_need_approval:
        interrupt_on = {name: True for name in tools_need_approval}
        logger.info(f"🔒 审批工具配置: {len(interrupt_on)} 个工具需要审批")
        return interrupt_on
    return None


def _get_skills_config() -> tuple:
    """
    获取 Skills 配置

    Returns:
        (project_root, skills_dir, has_skills, backend, skills)
    """
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


async def _create_agent(
    llm: BaseChatModel,
    system_prompt: str,
    tools: List[Any],
    subagents: List[Dict[str, Any]],
    middleware: List[Any],
    interrupt_on: Optional[Dict[str, bool]],
) -> Any:
    """创建 DeepAgents 实例"""
    checkpointer = await get_checkpointer()

    # 获取 Store 适配器

    store = get_langgraph_store()
    logger.info("🧠 SQLite FTS5 Store 适配器已加载（全文搜索，零外部依赖）")

    # 获取 Skills 配置
    project_root, _, _, backend, skills = _get_skills_config()

    # 创建 Agent
    agent = create_deep_agent(
        name="OpsAgent",
        model=llm,
        system_prompt=system_prompt,
        tools=tools,
        subagents=subagents,
        middleware=middleware,
        checkpointer=checkpointer,
        interrupt_on=interrupt_on,
        store=store,
        backend=backend,
        skills=skills,
    )

    logger.info("✅ Agent 创建完成（动态模式，无缓存）")
    return agent


# ========== 主入口函数 ==========

async def get_ops_agent(
    llm: Optional[BaseChatModel] = None,
    enable_approval: bool = True,
    user_permissions: Optional[Set[str]] = None,
    user_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> Any:
    """
    获取 Ops Agent（动态创建，每次请求都从数据库读取最新审批配置）

    每次调用都会重新创建 Agent，确保使用最新的审批配置。
    所有会话通过 checkpointer + thread_id 区分会话状态。

    Args:
        llm: 语言模型实例 (默认使用 LLMFactory)
        enable_approval: 是否启用 interrupt_on 批准流程
        user_permissions: 用户权限代码集合（静态权限）
        user_id: 用户 ID（用于动态获取权限）
        db: 数据库会话（用于动态获取权限）

    Returns:
        编译后的 DeepAgents 图
    """
    logger.info("🔄 动态创建 Agent（每次请求都读取最新审批配置）")
    logger.info(
        f"🔍 调试参数: enable_approval={enable_approval}, "
        f"user_id={user_id}, user_permissions={user_permissions}"
    )

    # 1. 获取 LLM
    llm = _get_llm(llm)

    # 2. 加载组件（带缓存）
    subagents = _load_subagents()
    tools = _load_tools(user_id, db, user_permissions)
    middleware = _load_middleware()

    # 3. 获取审批配置
    tools_need_approval = _get_tools_need_approval(enable_approval, user_id)

    # 4. 构建系统提示词
    system_prompt = _build_system_prompt(tools_need_approval)

    # 5. 输出工具信息
    _log_tools_info(tools)

    # 6. 构建 interrupt_on 配置
    interrupt_on = _build_interrupt_on(tools_need_approval)

    # 7. 创建 Agent
    agent = await _create_agent(
        llm=llm,
        system_prompt=system_prompt,
        tools=tools,
        subagents=subagents,
        middleware=middleware,
        interrupt_on=interrupt_on,
    )

    return agent


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

    使用 CoT + Plan-and-Solve 模式处理用户请求：
    - Comprehension: 理解用户需求
    - CoT Reasoning: 显式推理分析
    - Planning: 生成执行计划
    - Evaluation: 评估计划质量
    - Delegation: 委派给子智能体
    - Monitoring: 监控执行进度
    - Synthesis: 整合结果

    Args:
        user_query: 用户查询
        context: 上下文信息
        enable_cot: 是否启用 CoT 推理
        enable_plan_evaluation: 是否启用计划评估

    Returns:
        处理结果，包含推理摘要和执行详情
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
    "MAIN_AGENT_ENHANCED_CONFIG",
    "enhanced_main_agent_process",
]
