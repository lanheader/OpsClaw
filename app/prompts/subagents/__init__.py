"""
Subagents 提示词模块
"""

from .intent import INTENT_AGENT_PROMPT
from .data import DATA_AGENT_PROMPT
from .analyze import ANALYZE_AGENT_PROMPT
from .execute import EXECUTE_AGENT_PROMPT
from .report import REPORT_AGENT_PROMPT
from .format import FORMAT_AGENT_PROMPT

__all__ = [
    "INTENT_AGENT_PROMPT",
    "DATA_AGENT_PROMPT",
    "ANALYZE_AGENT_PROMPT",
    "EXECUTE_AGENT_PROMPT",
    "REPORT_AGENT_PROMPT",
    "FORMAT_AGENT_PROMPT",
]
