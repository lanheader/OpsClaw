"""
Execute Agent - 执行操作子智能体
执行修复命令,监控执行结果

v3.1 变更：增加 K8s 读工具，用于验证执行结果
⭐ system_prompt 将动态从数据库加载，经过 DSPy 优化
"""

from app.tools import get_tools_by_group

EXECUTE_AGENT_CONFIG = {
    "name": "execute-agent",
    "description": "执行修复命令,监控执行结果（支持验证执行结果）",
    "system_prompt": None,  # 将动态从数据库加载
    "tools": [
        # K8s 写操作和删除操作工具
        *get_tools_by_group("k8s.write"),
        *get_tools_by_group("k8s.delete"),
        *get_tools_by_group("k8s.update"),
        # 增加读工具：用于验证执行结果
        *get_tools_by_group("k8s.read"),
    ],
}
