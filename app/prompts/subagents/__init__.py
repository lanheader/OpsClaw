"""
Subagents 提示词模块（精简版 v3.1）

只保留 3 个 subagent 的提示词：
- data-agent: 数据采集
- analyze-agent: 分析诊断
- execute-agent: 执行操作
"""

from .data import DATA_AGENT_PROMPT
from .analyze import ANALYZE_AGENT_PROMPT
from .execute import EXECUTE_AGENT_PROMPT

__all__ = [
    "DATA_AGENT_PROMPT",
    "ANALYZE_AGENT_PROMPT",
    "EXECUTE_AGENT_PROMPT",
]
