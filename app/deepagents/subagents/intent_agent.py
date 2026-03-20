"""
Intent Agent - 意图识别子智能体
识别用户输入的意图类型和提取实体
"""

from app.prompts.subagents.intent import INTENT_AGENT_PROMPT

INTENT_AGENT_CONFIG = {
    "name": "intent-agent",
    "description": "识别用户输入的意图类型（query/diagnose/operate/unknown）并提取相关实体",
    "system_prompt": INTENT_AGENT_PROMPT,
    "tools": [],  # 不需要工具,纯推理
}
