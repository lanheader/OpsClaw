"""
Report Agent - 报告生成子智能体
生成结构化报告
"""

from app.prompts.subagents.report import REPORT_AGENT_PROMPT

REPORT_AGENT_CONFIG = {
    "name": "report-agent",
    "description": "生成结构化报告（Markdown 格式）",
    "system_prompt": REPORT_AGENT_PROMPT,
    "tools": [],  # 不需要工具,纯推理
}
