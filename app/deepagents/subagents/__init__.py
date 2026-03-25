"""
Subagents 注册和管理
"""

import logging
from typing import List, Dict
from deepagents import SubAgent

from app.core.llm_factory import LLMFactory
from app.services.unified_prompt_optimizer import get_prompt_optimizer
from .data_agent import DATA_AGENT_CONFIG
from .analyze_agent import ANALYZE_AGENT_CONFIG
from .execute_agent import EXECUTE_AGENT_CONFIG

logger = logging.getLogger(__name__)


def _load_prompt(subagent_name: str) -> str:
    """
    加载提示词

    Args:
        subagent_name: 子智能体名称

    Returns:
        提示词内容
    """
    optimizer = get_prompt_optimizer()
    return optimizer.get_prompt_for_agent(subagent_name)


def get_all_subagents() -> List[SubAgent]:
    """
    获取所有子智能体配置

    Returns:
        子智能体配置列表
    """
    # 获取原始配置（不包含 system_prompt，稍后动态注入）
    configs: List[SubAgent] = [
        DATA_AGENT_CONFIG.copy(),
        ANALYZE_AGENT_CONFIG.copy(),
        EXECUTE_AGENT_CONFIG.copy(),
    ]

    # 为每个 subagent 注入专用 LLM 和提示词
    for config in configs:
        subagent_name = config["name"]

        # 从静态文件加载提示词
        prompt = _load_prompt(subagent_name)
        config["system_prompt"] = prompt

        # 注入专用 LLM
        config["model"] = LLMFactory.create_llm_for_subagent(subagent_name)

        if subagent_name == "data-agent":
            config["tools"] = DATA_AGENT_CONFIG["tools"]
        elif subagent_name == "analyze-agent":
            config["tools"] = ANALYZE_AGENT_CONFIG["tools"]
        elif subagent_name == "execute-agent":
            config["tools"] = EXECUTE_AGENT_CONFIG["tools"]

        logger.info(f"✅ {subagent_name} 配置完成 (提示词长度: {len(prompt)} 字符)")

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
    "DATA_AGENT_CONFIG",
    "ANALYZE_AGENT_CONFIG",
    "EXECUTE_AGENT_CONFIG",
]
