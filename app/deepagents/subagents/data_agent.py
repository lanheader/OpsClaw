"""
Data Agent - 数据采集子智能体

功能：
1. 调用 K8s/Prometheus/Loki 工具获取集群数据
2. 通过 deepagents 内置 ReAct 循环实现并行数据采集
3. 整合结果供 analyze-agent 使用

⭐ system_prompt 将动态从数据库加载
⭐ 工具按集成开关动态加载
"""

# 基础配置（工具延迟加载）
DATA_AGENT_CONFIG = {
    "name": "data-agent",
    "description": "执行数据采集命令,调用 K8s/Prometheus/Loki 工具获取集群数据",
    "system_prompt": None,  # 将动态从数据库加载
    "tools": [],  # 将在 get_all_subagents 中动态加载
    "tool_packages": ["k8s", "prometheus", "loki"],  # 需要加载的工具包
}

__all__ = [
    "DATA_AGENT_CONFIG",
]
