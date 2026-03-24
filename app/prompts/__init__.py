# app/prompts/__init__.py
"""提示词管理模块（精简版 v3.1）

DeepAgents 架构的提示词导出。

实际的提示词定义在：
- app/prompts/main_agent.py - 主智能体提示词
- app/prompts/subagents/ - 子智能体提示词 (3 个)

架构说明：
- 主智能体直接理解用户意图（无需 intent-agent）
- 主智能体直接格式化输出（无需 format-agent）
- 主智能体直接生成报告（无需 report-agent）
"""

# 导出主智能体提示词
from app.prompts.main_agent import MAIN_AGENT_SYSTEM_PROMPT

# 导出子智能体提示词（精简版 v3.1）
from app.prompts.subagents import (
    DATA_AGENT_PROMPT,
    ANALYZE_AGENT_PROMPT,
    EXECUTE_AGENT_PROMPT,
)

__all__ = [
    "MAIN_AGENT_SYSTEM_PROMPT",
    "DATA_AGENT_PROMPT",
    "ANALYZE_AGENT_PROMPT",
    "EXECUTE_AGENT_PROMPT",
]
