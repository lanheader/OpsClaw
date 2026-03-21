"""
Data Agent - 数据采集子智能体
执行数据采集命令,调用 K8s/Prometheus/Loki 工具
"""

from app.prompts.subagents.data import DATA_AGENT_PROMPT
from app.tools import get_all_tools

DATA_AGENT_CONFIG = {
    "name": "data-agent",
    "description": "执行数据采集命令,调用 K8s/Prometheus/Loki 工具获取集群数据",
    "system_prompt": DATA_AGENT_PROMPT,
    "tools": [
        *get_all_tools(),
    ],
}
