"""
Analyze Agent - 分析决策子智能体

功能：
1. 分析采集的数据，诊断问题根因
2. 通过 deepagents 内置 ReAct 循环实现多路径诊断
3. 通过 Skills 系统获取排查经验
4. 生成修复建议

⭐ system_prompt 将动态从数据库加载
⭐ 工具按集成开关动态加载
"""

# 基础配置（工具延迟加载）
ANALYZE_AGENT_CONFIG = {
    "name": "analyze-agent",
    "description": "分析采集的数据,诊断问题根因,生成修复建议",
    "system_prompt": None,  # 将动态从数据库加载
    "tools": [],  # 将在 get_all_subagents 中动态加载
    "tool_groups": ["k8s.read"],  # 需要加载的工具组
}

__all__ = [
    "ANALYZE_AGENT_CONFIG",
]
