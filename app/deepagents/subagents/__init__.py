"""
Subagents 注册和管理
"""

from typing import List
from deepagents import SubAgent
from app.core.llm_factory import LLMFactory

from .intent_agent import INTENT_AGENT_CONFIG
from .data_agent import DATA_AGENT_CONFIG
from .analyze_agent import ANALYZE_AGENT_CONFIG
from .execute_agent import EXECUTE_AGENT_CONFIG
from .report_agent import REPORT_AGENT_CONFIG
from .format_agent import FORMAT_AGENT_CONFIG


def get_all_subagents() -> List[SubAgent]:
    """
    获取所有子智能体配置，并为每个 subagent 注入专用 LLM

    Returns:
        子智能体配置列表（每个配置包含 model 字段）
    """
    configs: List[SubAgent] = [
        INTENT_AGENT_CONFIG,
        DATA_AGENT_CONFIG,
        ANALYZE_AGENT_CONFIG,
        EXECUTE_AGENT_CONFIG,
        REPORT_AGENT_CONFIG,
        FORMAT_AGENT_CONFIG,
    ]

    # 为每个 subagent 注入专用 LLM
    for config in configs:
        subagent_name = config["name"]
        config["model"] = LLMFactory.create_llm_for_subagent(subagent_name)

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


__all__ = [
    "get_all_subagents",
    "get_subagent_by_name",
    "INTENT_AGENT_CONFIG",
    "DATA_AGENT_CONFIG",
    "ANALYZE_AGENT_CONFIG",
    "EXECUTE_AGENT_CONFIG",
    "REPORT_AGENT_CONFIG",
    "FORMAT_AGENT_CONFIG",
]
