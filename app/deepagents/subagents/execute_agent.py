"""
Execute Agent - 执行操作子智能体
执行修复命令,监控执行结果
"""

from app.prompts.subagents.execute import EXECUTE_AGENT_PROMPT
from app.tools import get_k8s_tools, get_command_executor_tools

EXECUTE_AGENT_CONFIG = {
    "name": "execute-agent",
    "description": "执行修复命令,监控执行结果",
    "system_prompt": EXECUTE_AGENT_PROMPT,
    "tools": [
        *get_k8s_tools(),
        *get_command_executor_tools(),
    ],
}
