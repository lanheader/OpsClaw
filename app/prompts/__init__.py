# app/prompts/__init__.py
"""提示词管理模块

DeepAgents 架构的提示词导出。

实际的提示词定义在：
- app/prompts/main_agent.py - 主智能体提示词
- app/prompts/subagents/ - 子智能体提示词
"""

# 导出主智能体提示词
from app.prompts.main_agent import MAIN_AGENT_SYSTEM_PROMPT

# 导出子智能体提示词
from app.prompts.subagents import (
    INTENT_AGENT_PROMPT,
    DATA_AGENT_PROMPT,
    ANALYZE_AGENT_PROMPT,
    EXECUTE_AGENT_PROMPT,
    REPORT_AGENT_PROMPT,
    FORMAT_AGENT_PROMPT,
)

__all__ = [
    "MAIN_AGENT_SYSTEM_PROMPT",
    "INTENT_AGENT_PROMPT",
    "DATA_AGENT_PROMPT",
    "ANALYZE_AGENT_PROMPT",
    "EXECUTE_AGENT_PROMPT",
    "REPORT_AGENT_PROMPT",
    "FORMAT_AGENT_PROMPT",
]
