"""
Network Agent - 网络排查子智能体

功能：
1. DNS 解析问题排查
2. Service 互通问题排查
3. Ingress 配置问题排查
4. 网络策略问题排查

利用 deepagents 内置的 ReAct 循环 + Skills 系统进行网络诊断。
"""

from app.tools import get_tools_by_package

NETWORK_AGENT_CONFIG = {
    "name": "network-agent",
    "description": (
        "排查网络问题：DNS解析失败、Service间调用超时/拒绝连接、"
        "Ingress 404/502/503、跨Namespace通信失败、网络策略阻断。"
        "当用户提到网络不通、DNS失败、服务间调用异常、Ingress报错时使用。"
    ),
    "system_prompt": None,  # 将动态从数据库加载
    "tools": [
        # K8s 读操作（查看 Service、Endpoints、NetworkPolicy、Ingress 等）
        *get_tools_by_package("k8s"),
        # 可能需要日志排查
        *get_tools_by_package("loki"),
    ],
}

__all__ = ["NETWORK_AGENT_CONFIG"]
