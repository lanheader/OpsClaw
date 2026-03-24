"""
Analyze Agent - 分析决策子智能体
分析采集的数据,诊断问题根因,生成修复建议

v3.1 变更：增加 K8s 读工具，用于验证分析结论
⭐ system_prompt 将动态从数据库加载，经过 DSPy 优化
"""

from app.tools import get_tools_by_group

ANALYZE_AGENT_CONFIG = {
    "name": "analyze-agent",
    "description": "分析采集的数据,诊断问题根因,生成修复建议（支持验证分析结论）",
    "system_prompt": None,  # 将动态从数据库加载
    "tools": [
        # 增加读工具：用于验证分析结论
        *get_tools_by_group("k8s.read"),
    ],
}
