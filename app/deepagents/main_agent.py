"""
DeepAgents 主智能体配置

负责任务规划、子智能体委派、批准流程和智能路由

增强版（v3.2）：
- CoT (Chain of Thought): 显式推理链
- Plan-and-Solve: 详细任务规划
- Self-Reflection: 规划评估和调整
- 向量记忆: 长期记忆和知识库检索
- 记忆中间件: 自动增强上下文

⭐ system_prompt 将动态从数据库加载，经过 DSPy 优化
"""

from collections import defaultdict
from deepagents import create_deep_agent
from langchain_core.language_models import BaseChatModel
from typing import Any, Optional, Set
from sqlalchemy.orm import Session

from app.core.llm_factory import LLMFactory
from app.core.checkpointer import get_checkpointer
from app.core.constants import is_incident_handling
from app.prompts.main_agent import MAIN_AGENT_SYSTEM_PROMPT
from app.deepagents.subagents import get_all_subagents
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.message_trimming_middleware import MessageTrimmingMiddleware
from app.middleware.context_compression_middleware import ContextCompressionMiddleware
from app.middleware.error_filtering_middleware import ErrorFilteringMiddleware
from app.middleware.memory_middleware import MemoryEnhancedAgent
from app.tools.registry import get_tool_registry
from app.tools.base import RiskLevel
from app.utils.logger import get_logger
from app.services.enhanced_main_agent_service import get_enhanced_main_agent_service
from app.services.approval_config_service import ApprovalConfigService
from app.models.database import SessionLocal
from app.models.user import User
from app.memory.memory_manager import get_memory_manager

logger = get_logger(__name__)

# 单例 agent（所有会话共享同一个编译图，通过 thread_id 区分会话）
_agent: Optional[Any] = None


async def get_ops_agent(
    llm: Optional[BaseChatModel] = None,
    enable_approval: bool = True,
    user_permissions: Optional[Set[str]] = None,
    user_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> Any:
    """
    获取 Ops Agent 单例（懒加载，异步）

    所有会话共享同一个编译图，通过 checkpointer + thread_id 区分会话状态。
    checkpointer 由 CheckpointerFactory 管理，默认使用 SQLite 持久化。

    Args:
        llm: 语言模型实例 (默认使用 LLMFactory)
        enable_approval: 是否启用 interrupt_on 批准流程
        user_permissions: 用户权限代码集合，用于过滤可用工具（静态权限）
        user_id: 用户 ID（用于动态获取权限）
        db: 数据库会话（用于动态获取权限）

    Returns:
        编译后的 DeepAgents 图
    """
    global _agent

    # 注意：如果传入了 user_permissions 或 user_id，不使用缓存的 agent
    # 因为不同用户的权限不同，需要动态创建 agent
    if _agent is not None and user_permissions is None and user_id is None:
        return _agent

    if llm is None:
        # 使用默认 LLM provider（不再使用 profile）
        llm = LLMFactory.create_llm()

    subagents = get_all_subagents()

    # ========== 输出可用 Subagent 列表 ==========
    logger.info("=" * 60)
    logger.info("🤖 主智能体可用 Subagent 列表:")
    logger.info("=" * 60)
    for subagent in subagents:
        name = subagent.get('name', 'unknown')
        desc = subagent.get('description', 'No description')
        tool_count = len(subagent.get('tools', []))
        logger.info(f"  - {name}: {desc}")
        logger.info(f"    工具数量: {tool_count}")
    logger.info(f"📊 总计: {len(subagents)} 个 Subagent")
    logger.info("=" * 60)
    print(f"[MainAgent] ✅ 加载 {len(subagents)} 个 Subagent", flush=True)

    # ========== 从 ToolRegistry 获取工具 ==========
    registry = get_tool_registry()

    # 优先使用动态权限（user_id + db），否则使用静态权限（user_permissions）
    if user_id is not None and db is not None:
        # 动态权限：从数据库获取用户权限
        logger.info(f"🔐 使用动态权限过滤工具（user_id: {user_id}）")
        tools = registry.get_langchain_tools(user_id=user_id, db=db)
    elif user_permissions is not None:
        # 静态权限：使用传入的权限集合
        logger.info(
            f"🔐 使用静态权限过滤工具 "
            f"(权限: {', '.join(sorted(user_permissions))})"
        )
        tools = registry.get_langchain_tools(permissions=user_permissions)
    else:
        # 无权限过滤：加载所有工具
        logger.info("✅ 未指定用户权限，加载所有工具")
        tools = registry.get_langchain_tools()

    logger.info(f"📊 加载工具数量: {len(tools)} 个")

    # 配置中间件（执行顺序：ErrorFiltering → Trimming → Logging）
    # 注意：不使用 ContextCompressionMiddleware，因为它与 DeepAgents 内置的
    # SummarizationMiddleware 冲突，会导致第二次 LLM 调用使用压缩后的上下文返回空内容
    middleware = [
        ErrorFilteringMiddleware(),  # 过滤工具调用错误消息
        MessageTrimmingMiddleware(max_messages=40),  # 保留最近 40 条消息
        LoggingMiddleware(),
    ]
    logger.info("✅ 错误消息过滤中间件已启用（过滤工具调用错误）")
    logger.info("✅ 消息截断中间件已启用（保留最近 40 条消息）")
    logger.info("✅ 日志中间件已启用")

    # 动态构建需要审批的工具列表（从数据库配置获取）
    interrupt_on = None
    if enable_approval:
        # 尝试从数据库获取审批配置
        tools_need_approval = set()
        config_db = SessionLocal()
        try:
            # 获取用户角色（如果有）
            user_role = None
            if user_id is not None and db is not None:
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    user_role = user.role

            # 从审批配置获取需要审批的工具
            tools_need_approval = ApprovalConfigService.get_tools_require_approval(
                config_db, user_role=user_role
            )
            logger.info(
                f"🔒 从审批配置获取需要审批的工具: {len(tools_need_approval)} 个"
            )
        except Exception as e:
            # 如果数据库查询失败，回退到基于风险等级的判断
            logger.warning(f"⚠️ 无法从数据库获取审批配置，使用风险等级判断: {e}")
            registry = get_tool_registry()
            for tool_class in registry.list_tools():
                metadata = tool_class.get_metadata()
                if metadata and metadata.risk_level == RiskLevel.HIGH:
                    tools_need_approval.add(metadata.name)
            logger.info(f"🔒 基于风险等级判断的高风险工具: {len(tools_need_approval)} 个")
        finally:
            config_db.close()

        if tools_need_approval:
            interrupt_on = {name: True for name in tools_need_approval}
        else:
            interrupt_on = None

    # ========== 输出可用工具列表 ==========
    logger.info("=" * 60)
    logger.info("🛠️  主智能体可用工具列表:")
    logger.info("=" * 60)

    # 从 ToolRegistry 获取分组信息并按分组显示
    tool_groups = defaultdict(list)
    registry = get_tool_registry()

    for tool in tools:
        tool_name = getattr(tool, 'name', 'unknown')
        # 从 registry 获取工具所属分组
        tool_class = registry.get_tool(tool_name)
        if tool_class:
            metadata = tool_class.get_metadata()
            if metadata:
                # 使用分组名称进行分类
                group_name = metadata.group.replace('.', ' ').title()
                tool_groups[group_name].append(tool_name)

    for group, tool_names in sorted(tool_groups.items()):
        logger.info(f"  [{group}] {len(tool_names)} 个:")
        for name in sorted(tool_names):
            logger.info(f"    - {name}")

    logger.info(f"📊 总计: {len(tools)} 个工具")
    logger.info("=" * 60)
    logger.info(f"[MainAgent] ✅ 主智能体初始化完成，可用工具: {len(tools)} 个")

    checkpointer = await get_checkpointer()

    agent = create_deep_agent(
        model=llm,
        system_prompt=MAIN_AGENT_SYSTEM_PROMPT,
        tools=tools,
        subagents=subagents,
        middleware=middleware,
        checkpointer=checkpointer,
        interrupt_on=interrupt_on,
    )

    # 只有在没有指定用户权限和 user_id 时才缓存 agent（全局默认 agent）
    if user_permissions is None and user_id is None:
        _agent = agent

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


MAIN_AGENT_ENHANCED_CONFIG = {
    "enable_cot": True,  # 启用 CoT 显式推理
    "enable_plan_evaluation": True,  # 启用计划评估
    "enable_reasoning_log": True,  # 启用推理链日志
    "max_reasoning_depth": 5,  # 最大推理深度
    "plan_evaluation_threshold": 0.7,  # 计划评估通过阈值
    "enable_memory": True,  # 启用向量记忆
    "enable_memory_middleware": True,  # 启用记忆中间件
    "enable_reflection": True,  # 启用 Self-Reflection
    "enable_auto_learn": True,  # 启用自动学习
    "memory_similarity_threshold": 0.7,  # 记忆检索相似度阈值
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

    示例:
        result = await enhanced_main_agent_process(
            user_query="检查生产环境的 Pod 状态并诊断问题",
            context={"namespace": "production"}
        )
        print(f"推理摘要: {result['reasoning_summary']}")
        print(f"子任务完成: {result['subtasks_completed']}")
    """


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
    "get_ops_agent_enhanced",  # 新增：带记忆增强的 agent
    "execute_with_memory",  # 新增：带记忆的执行函数
]


# ==================== 记忆增强功能 ====================

async def get_ops_agent_enhanced(
    llm=None,
    enable_approval: bool = True,
    user_permissions: Optional[Set[str]] = None,
    user_id: Optional[int] = None,
    db: Optional[Session] = None,
    enable_memory: bool = True,
    enable_reflection: bool = True,
    enable_auto_learn: bool = True
) -> Any:
    """
    获取增强版 Ops Agent（带记忆和反思）

    新增参数：
        enable_memory: 启用向量记忆
        enable_reflection: 启用自检机制
        enable_auto_learn: 启用自动学习
    """
    # 获取基础 agent
    agent = await get_ops_agent(
        llm=llm,
        enable_approval=enable_approval,
        user_permissions=user_permissions,
        user_id=user_id,
        db=db
    )

    # 如果启用记忆增强，包装 agent
    if enable_memory:
        agent = MemoryEnhancedAgent(
            agent=agent,
            enable_memory=True,
            enable_auto_learn=enable_auto_learn
        )
        logger.info("🧠 [MemoryEnhancedAgent] 已启用记忆增强")

    return agent


async def execute_with_memory(
    agent,
    user_input: str,
    session_id: str,
    user_id: int = None
) -> Any:
    """
    带记忆增强的执行

    Args:
        agent: Agent 实例
        user_input: 用户输入
        session_id: 会话 ID
        user_id: 用户 ID

    Returns:
        执行结果
    """
    memory_manager = get_memory_manager(user_id=str(user_id))

    # 1. 构建上下文（检索相关记忆 - 包含 Mem0）
    context = await memory_manager.build_context(
        user_query=user_input,
        session_id=session_id,
        include_incidents=True,
        include_knowledge=True,
        include_session=True,
        include_mem0=True  # 启用 Mem0 通用对话记忆
    )

    # 2. 如果有相关记忆，增强输入
    enhanced_input = user_input
    if context:
        enhanced_input = f"""{user_input}

---
**参考资料**（来自历史对话和知识库）：
{context}
---
"""
        logger.info("🧠 [execute_with_memory] 输入已增强")

    # 3. 执行 Agent
    config = {"configurable": {"thread_id": session_id}}
    result = await agent.ainvoke(
        {"messages": [("user", enhanced_input)]},
        config=config
    )

    # 4. 自动学习（包含 Mem0 和 MemoryManager）
    try:
        # 构建对话消息列表
        messages = result.get("messages", [])
        conversation_messages = [
            {"role": "user", "content": user_input}
        ]

        # 添加 AI 响应消息
        for msg in messages:
            if hasattr(msg, "content"):
                conversation_messages.append({"role": "assistant", "content": msg.content})
            elif isinstance(msg, dict) and "content" in msg:
                conversation_messages.append({"role": "assistant", "content": msg["content"]})

        await memory_manager.auto_learn_from_result(
            user_query=user_input,
            result={"messages": messages},
            session_id=session_id,
            messages=conversation_messages  # 传递完整对话给 Mem0
        )

        logger.info("🤖 [execute_with_memory] 已自动学习处理经验")
    except Exception as e:
        logger.warning(f"⚠️ 自动学习失败: {e}")

    return result

