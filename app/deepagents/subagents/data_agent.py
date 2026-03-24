"""
Data Agent - 数据采集子智能体
执行数据采集命令,调用 K8s/Prometheus/Loki 工具

⭐ system_prompt 将动态从数据库加载，经过 DSPy 优化
"""

from app.tools import get_tools_by_package

# 按包获取数据采集工具（只包含读操作）
DATA_AGENT_CONFIG = {
    "name": "data-agent",
    "description": "执行数据采集命令,调用 K8s/Prometheus/Loki 工具获取集群数据",
    "system_prompt": None,  # 将动态从数据库加载
    "tools": [
        # K8s 读操作
        *get_tools_by_package("k8s"),
        # Prometheus 查询
        *get_tools_by_package("prometheus"),
        # Loki 日志查询
        *get_tools_by_package("loki"),
    ],
}
