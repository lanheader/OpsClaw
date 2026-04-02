"""
Storage Agent - 存储排查子智能体

功能：
1. PVC/PV 状态排查
2. StorageClass 问题排查
3. 磁盘空间分析
4. 持久化挂载问题排查

利用 deepagents 内置的 ReAct 循环 + Skills 系统进行存储诊断。

⭐ 工具按集成开关动态加载
"""

# 基础配置（工具延迟加载）
STORAGE_AGENT_CONFIG = {
    "name": "storage-agent",
    "description": (
        "排查存储问题：PVC Pending/绑定失败、Pod挂载失败、磁盘空间不足、"
        "StorageClass 配置问题、Volume 快照问题。"
        "当用户提到存储、磁盘、PVC、PV、挂载、volume 时使用。"
    ),
    "system_prompt": None,  # 将动态从数据库加载
    "tools": [],  # 将在 get_all_subagents 中动态加载
    "tool_packages": ["k8s"],
}

__all__ = ["STORAGE_AGENT_CONFIG"]
