"""
DSPy 集成模块 - 为 DeepAgents Subagents 提供 DSPy 优化能力

这个模块提供了 DSPy 框架与 Ops Agent 的集成，包括：
- LLM 适配器（将 LangChain LLM 包装为 DSPy LLM）
- DSPy 模块（Data、Analyze、Execute）
- 训练数据收集器
- 提示词优化器（通过 unified_prompt_optimizer.py）

提示词优化流程：
    1. 用户交互时自动收集训练数据
    2. 达到阈值时自动触发优化
    3. 优化结果保存到数据库（subagent_prompts 表）
    4. Agent 使用时自动加载最新的优化版本

使用方式：
    # 优化提示词
    from app.services.unified_prompt_optimizer import trigger_manual_optimization
    log = await trigger_manual_optimization("data-agent")

    # DeepAgents 会自动加载优化后的提示词
    # (无需手动操作，通过 subagents/__init__.py 自动处理)
"""

import logging
from typing import Optional, Dict, Any

try:
    import dspy
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False
    dspy = None

from app.dspy.llm_adapter import create_dspy_llm, create_dspy_llm_for_subagent, DriverLM

logger = logging.getLogger(__name__)

# 全局配置
_configured = False
_default_llm: Optional[DriverLM] = None


def configure_dspy(
    langchain_llm=None,
    subagent_name: Optional[str] = None,
) -> bool:
    """
    配置 DSPy 的默认 LLM

    Args:
        langchain_llm: LangChain LLM 实例（可选）
        subagent_name: 子智能体名称（如果提供，则使用该子智能体的 LLM）

    Returns:
        是否配置成功
    """
    global _configured, _default_llm

    if not DSPY_AVAILABLE:
        logger.warning("DSPy 未安装，无法配置")
        return False

    try:
        if subagent_name:
            _default_llm = create_dspy_llm_for_subagent(subagent_name)
        elif langchain_llm:
            _default_llm = create_dspy_llm(langchain_llm)
        else:
            # 使用默认的 data-agent LLM
            _default_llm = create_dspy_llm_for_subagent("data-agent")

        # 配置 DSPy
        dspy.settings.configure(lm=_default_llm)
        _configured = True

        logger.info(f"DSPy 已配置，使用 LLM: {_default_llm.get_model_info()}")
        return True

    except Exception as e:
        logger.error(f"配置 DSPy 时出错: {e}")
        return False


def is_dspy_available() -> bool:
    """检查 DSPy 是否可用"""
    return DSPY_AVAILABLE


def is_configured() -> bool:
    """检查 DSPy 是否已配置"""
    return _configured


def get_default_llm() -> Optional[DriverLM]:
    """获取默认的 DSPy LLM"""
    return _default_llm


__all__ = [
    "DSPY_AVAILABLE",
    "configure_dspy",
    "is_dspy_available",
    "is_configured",
    "get_default_llm",
    "create_dspy_llm",
    "create_dspy_llm_for_subagent",
    "DriverLM",
]

# 尝试自动配置（如果 LLMFactory 可用）
try:
    from app.core.llm_factory import LLMFactory
    if DSPY_AVAILABLE and not _configured:
        configure_dspy(subagent_name="data-agent")
except ImportError:
    pass
except Exception as e:
    logger.debug(f"自动配置 DSPy 失败（这是正常的，稍后可以手动配置）: {e}")
