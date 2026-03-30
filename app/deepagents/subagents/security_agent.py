"""
Security Agent - 安全巡检子智能体

功能：
1. RBAC 权限审计
2. 安全配置检查
3. 镜像安全扫描
4. 敏感信息泄露检查

利用 deepagents 内置的 ReAct 循环进行安全诊断。
"""

from app.tools import get_tools_by_package

SECURITY_AGENT_CONFIG = {
    "name": "security-agent",
    "description": (
        "执行安全巡检：RBAC权限审计、Pod安全策略检查、镜像漏洞扫描、"
        "敏感信息泄露检查、网络策略合规审计。"
        "当用户提到安全、权限、漏洞、合规、审计、RBAC 时使用。"
    ),
    "system_prompt": None,  # 将动态从数据库加载
    "tools": [
        *get_tools_by_package("k8s"),
    ],
}

__all__ = ["SECURITY_AGENT_CONFIG"]
