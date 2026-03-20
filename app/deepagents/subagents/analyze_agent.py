"""
Analyze Agent - 分析决策子智能体
分析采集的数据,诊断问题根因,生成修复建议
"""

from app.prompts.subagents.analyze import ANALYZE_AGENT_PROMPT

ANALYZE_AGENT_CONFIG = {
    "name": "analyze-agent",
    "description": "分析采集的数据,诊断问题根因,生成修复建议",
    "system_prompt": ANALYZE_AGENT_PROMPT,
    "tools": [],  # 不需要工具,纯推理
}
