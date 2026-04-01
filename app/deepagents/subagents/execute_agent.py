"""
Execute Agent - 执行操作子智能体

功能：
1. 执行 K8s 写操作、删除操作、更新操作
2. 通过 deepagents 内置 ReAct 循环实现安全执行
3. 高风险操作由 interrupt_on 拦截审批

⭐ system_prompt 将动态从数据库加载
⭐ 工具按集成开关动态加载
"""

# 基础配置（工具延迟加载）
EXECUTE_AGENT_CONFIG = {
    "name": "execute-agent",
    "description": "执行修复命令,监控执行结果（支持风险评估、执行验证、自动回滚）",
    "system_prompt": None,  # 将动态从数据库加载
    "tools": [],  # 将在 get_all_subagents 中动态加载
    "tool_groups": ["k8s.write", "k8s.delete", "k8s.update", "k8s.read"],  # 需要加载的工具组
}

__all__ = [
    "EXECUTE_AGENT_CONFIG",
]
