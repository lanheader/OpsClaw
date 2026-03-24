"""
Subagents 注册和管理（v3.2 - 数据库提示词管理）

变更说明：
- ❌ 删除 intent-agent：由主智能体直接理解意图
- ❌ 删除 report-agent：由主智能体直接生成报告
- ❌ 删除 format-agent：由主智能体直接格式化输出
- ✅ analyze-agent 增加读工具：用于验证分析结论
- ✅ execute-agent 增加读工具：用于验证执行结果
- ✅ 提示词数据库管理：提示词存储在数据库，Web 可编辑 ⭐ v3.2
- ✅ DSPy 实时优化：每次获取 subagent 时动态加载优化提示词
"""

import logging
from typing import List, Dict
from deepagents import SubAgent
from app.core.llm_factory import LLMFactory
from app.services.prompt_management import initialize_prompts
from .data_agent import DATA_AGENT_CONFIG
from .analyze_agent import ANALYZE_AGENT_CONFIG
from .execute_agent import EXECUTE_AGENT_CONFIG

logger = logging.getLogger(__name__)

# 检查 DSPy 是否可用
try:
    import dspy
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False


def _load_optimized_prompt(subagent_name: str) -> str:
    """
    加载优化后的提示词（内部函数）

    ⭐ 使用统一优化服务 UnifiedPromptOptimizer

    Args:
        subagent_name: 子智能体名称

    Returns:
        优化后的提示词
    """
    from app.services.unified_prompt_optimizer import get_prompt_optimizer

    optimizer = get_prompt_optimizer()
    return optimizer.get_prompt_for_agent(subagent_name)


def get_all_subagents() -> List[SubAgent]:
    """
    获取所有子智能体配置

    ⭐ 关键变更：完全基于数据库，不再使用静态文件

    流程：
    1. 初始化提示词数据库（从静态文件导入初始值）
    2. 从数据库读取基础提示词
    3. 调用 DSPy 进行优化
    4. 注入优化后的提示词到配置

    Returns:
        子智能体配置列表
    """
    # 初始化提示词数据库（从静态文件导入初始值）
    try:

        initialize_prompts()
        logger.info("✅ 提示词数据库已初始化")
    except Exception as e:
        logger.warning(f"提示词数据库初始化失败: {e}")

    # 获取原始配置（不包含 system_prompt，稍后动态注入）
    configs: List[SubAgent] = [
        DATA_AGENT_CONFIG.copy(),
        ANALYZE_AGENT_CONFIG.copy(),
        EXECUTE_AGENT_CONFIG.copy(),
    ]

    # 为每个 subagent 注入专用 LLM 和动态优化提示词
    for config in configs:
        subagent_name = config["name"]

        # 🔑 关键：从数据库加载并优化提示词（完全不使用静态文件）
        optimized_prompt = _load_optimized_prompt(subagent_name)
        config["system_prompt"] = optimized_prompt

        # 注入专用 LLM
        config["model"] = LLMFactory.create_llm_for_subagent(subagent_name)

        if subagent_name == "data-agent":
            config["tools"] = DATA_AGENT_CONFIG["tools"]
        elif subagent_name == "analyze-agent":
            config["tools"] = ANALYZE_AGENT_CONFIG["tools"]
        elif subagent_name == "execute-agent":
            config["tools"] = EXECUTE_AGENT_CONFIG["tools"]

        logger.info(f"✅ {subagent_name} 配置完成 (提示词长度: {len(optimized_prompt)} 字符)")

    return configs


def get_subagent_by_name(name: str) -> SubAgent:
    """
    根据名称获取子智能体配置

    Args:
        name: 子智能体名称

    Returns:
        子智能体配置
    """
    subagents = get_all_subagents()
    for subagent in subagents:
        if subagent["name"] == name:
            return subagent
    raise ValueError(f"Subagent '{name}' not found")


def is_dspy_optimization_enabled(subagent_name: str) -> bool:
    """
    检查指定 subagent 是否启用了 DSPy 优化

    Args:
        subagent_name: 子智能体名称

    Returns:
        是否启用 DSPy 优化
    """
    return DSPY_AVAILABLE


def get_subagent_prompt_info(subagent_name: str) -> dict:
    """
    获取 subagent 的提示词信息

    Args:
        subagent_name: 子智能体名称

    Returns:
        提示词信息字典
    """
    from app.models.database import get_db
    from app.models.subagent_prompt import SubagentPrompt
    from sqlalchemy import and_

    info = {
        "subagent_name": subagent_name,
        "dspy_available": DSPY_AVAILABLE,
        "using_optimized": False,
        "optimized_versions": [],
    }

    # 从数据库查询优化版本
    db = next(get_db())
    try:
        optimized_prompts = (
            db.query(SubagentPrompt)
            .filter(
                and_(
                    SubagentPrompt.subagent_name == subagent_name,
                    SubagentPrompt.prompt_type == "optimized",
                )
            )
            .all()
        )

        info["optimized_versions"] = [p.version for p in optimized_prompts]
        info["using_optimized"] = any(p.is_latest and p.is_active for p in optimized_prompts)

    finally:
        db.close()

    return info


__all__ = [
    "get_all_subagents",
    "get_subagent_by_name",
    "is_dspy_optimization_enabled",
    "get_subagent_prompt_info",
    "DATA_AGENT_CONFIG",
    "ANALYZE_AGENT_CONFIG",
    "EXECUTE_AGENT_CONFIG",
]
