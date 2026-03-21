"""
Execute Agent - 执行操作子智能体
执行修复命令,监控执行结果
"""

from app.prompts.subagents.execute import EXECUTE_AGENT_PROMPT
from app.tools import get_tools_by_group

EXECUTE_AGENT_CONFIG = {
    "name": "execute-agent",
    "description": "执行修复命令,监控执行结果",
    "system_prompt": EXECUTE_AGENT_PROMPT,
    "tools": [
        # 获取所有 K8s 写操作和删除操作工具
        *get_tools_by_group("k8s.write"),
        *get_tools_by_group("k8s.delete"),
        *get_tools_by_group("k8s.update"),
    ],
}
