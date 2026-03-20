"""
Format Agent - 响应格式化子智能体
将报告格式化为适配 Web UI 或飞书的格式
"""

from app.prompts.subagents.format import FORMAT_AGENT_PROMPT

FORMAT_AGENT_CONFIG = {
    "name": "format-agent",
    "description": "将报告格式化为适配 Web UI 或飞书的格式",
    "system_prompt": FORMAT_AGENT_PROMPT,
    "tools": [],  # 不需要工具,纯推理
}
