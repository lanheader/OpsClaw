"""
Subagents 注册和管理

工具延迟加载：在 get_all_subagents 时根据集成开关动态加载工具，
而不是在模块 import 时加载。
"""

import logging
from typing import List, Dict, Any
from deepagents import SubAgent

from app.core.llm_factory import LLMFactory
from app.services.unified_prompt_optimizer import get_prompt_optimizer
from .data_agent import DATA_AGENT_CONFIG
from .analyze_agent import ANALYZE_AGENT_CONFIG
from .execute_agent import EXECUTE_AGENT_CONFIG
from .network_agent import NETWORK_AGENT_CONFIG
from .storage_agent import STORAGE_AGENT_CONFIG
from .security_agent import SECURITY_AGENT_CONFIG

logger = logging.getLogger(__name__)

# 所有子智能体原始配置（不包含工具，工具动态加载）
_ALL_CONFIGS: List[Dict[str, Any]] = [
    DATA_AGENT_CONFIG,
    ANALYZE_AGENT_CONFIG,
    EXECUTE_AGENT_CONFIG,
    NETWORK_AGENT_CONFIG,
    STORAGE_AGENT_CONFIG,
    SECURITY_AGENT_CONFIG,
]


def _load_prompt(subagent_name: str) -> str:
    """加载提示词"""
    optimizer = get_prompt_optimizer()
    return optimizer.get_prompt_for_agent(subagent_name)


def _load_tools_for_config(config: Dict[str, Any], db=None) -> List[Any]:  # type: ignore[no-untyped-def]
    """
    根据配置动态加载工具（带集成开关检查）

    支持:
    - tool_packages: 按包名加载（如 ["k8s", "prometheus"]）
    - tool_groups: 按组名加载（如 ["k8s.read", "k8s.write"]）
    """
    from app.tools import get_tools_by_package, get_tools_by_group

    tools = []

    # 按 tool_packages 加载
    for pkg in config.get("tool_packages", []):
        try:
            pkg_tools = get_tools_by_package(pkg, db=db)
            tools.extend(pkg_tools)
            logger.info(f"  {config['name']}: 加载包 '{pkg}' → {len(pkg_tools)} 个工具")
        except Exception as e:
            logger.warning(f"  {config['name']}: 加载包 '{pkg}' 失败: {e}")

    # 按 tool_groups 加载
    for group in config.get("tool_groups", []):
        try:
            group_tools = get_tools_by_group(group, db=db)
            tools.extend(group_tools)
            logger.info(f"  {config['name']}: 加载组 '{group}' → {len(group_tools)} 个工具")
        except Exception as e:
            logger.warning(f"  {config['name']}: 加载组 '{group}' 失败: {e}")

    # 去重（同名工具只保留一个）
    seen = set()
    unique_tools = []
    for t in tools:
        name = getattr(t, 'name', str(t))
        if name not in seen:
            seen.add(name)
            unique_tools.append(t)

    return unique_tools


def _inject_tools_into_prompt(prompt: str, tools: List[Any]) -> str:
    """将动态加载的工具列表注入到提示词末尾"""
    if not tools:
        return prompt

    lines = ["\n\n## 当前可用工具\n"]
    for t in tools:
        name = getattr(t, "name", "unknown")
        description = getattr(t, "description", "")
        lines.append(f"- **{name}**: {description}")

    return prompt + "\n".join(lines)


def get_all_subagents(db=None) -> List[SubAgent]:  # type: ignore[no-untyped-def]
    """
    获取所有子智能体配置（工具动态加载）

    Args:
        db: 数据库会话（用于集成开关检查）

    Returns:
        子智能体配置列表
    """
    configs: List[SubAgent] = []

    for base_config in _ALL_CONFIGS:
        config = {**base_config}
        subagent_name = config["name"]

        # 动态加载提示词
        prompt = _load_prompt(subagent_name)

        # 注入专用 LLM
        config["model"] = LLMFactory.create_llm_for_subagent(subagent_name)

        # 动态加载工具（带集成开关检查）
        config["tools"] = _load_tools_for_config(config, db=db)

        # 将工具信息注入到提示词中
        config["system_prompt"] = _inject_tools_into_prompt(prompt, config["tools"])

        # 清理内部字段
        config.pop("tool_packages", None)
        config.pop("tool_groups", None)

        logger.info(
            f"✅ {subagent_name} 配置完成 "
            f"(工具数: {len(config['tools'])}, 提示词长度: {len(prompt)} 字符)"
        )

        configs.append(config)  # type: ignore[arg-type]

    return configs


def get_subagent_by_name(name: str, db=None) -> SubAgent:  # type: ignore[no-untyped-def]
    """
    根据名称获取子智能体配置

    Args:
        name: 子智能体名称
        db: 数据库会话（用于集成开关检查）

    Returns:
        子智能体配置
    """
    subagents = get_all_subagents(db=db)
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
    "NETWORK_AGENT_CONFIG",
    "STORAGE_AGENT_CONFIG",
    "SECURITY_AGENT_CONFIG",
]
