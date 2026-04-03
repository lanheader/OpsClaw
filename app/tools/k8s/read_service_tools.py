"""
K8s Service/Ingress 读操作工具

包含 Service 和 Ingress 相关的查询工具：
- GetServicesTool: 获取 Service 列表
- GetIngressTool: 获取 Ingress 列表
"""

from typing import Dict, Any

from app.tools.base import (
    BaseOpTool,
    register_tool,
    OperationType,
    RiskLevel,
    tool_success_response,
    tool_error_response,
)
from app.tools.k8s.common import init_k8s_client, log_tool_start, log_tool_success


@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 Kubernetes Service 列表",
    examples=[
        "get_services(namespace='default')",
        "get_services(namespace='production')",
    ],
)
class GetServicesTool(BaseOpTool):
    """获取 Service 列表工具"""

    def __init__(self, db=None):  # type: ignore[no-untyped-def]
        self.k8s_client = init_k8s_client(db)

    async def execute(  # type: ignore[no-untyped-def]
        self,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        log_tool_start("get_services", namespace=namespace)
        try:
            services = self.k8s_client.core_v1.list_namespaced_service(namespace=namespace)

            data = [
                {
                    "name": service.metadata.name,
                    "namespace": service.metadata.namespace,
                    "type": service.spec.type,
                    "cluster_ip": service.spec.cluster_ip,
                    "ports": [
                        {
                            "name": port.name,
                            "port": port.port,
                            "protocol": port.protocol,
                        }
                        for port in (service.spec.ports or [])
                    ],
                }
                for service in services.items
            ]

            log_tool_success("get_services", len(data))
            return await tool_success_response(data, "get_services", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_services",
                context={"namespace": namespace}
            )


@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 Kubernetes Ingress 列表",
    examples=[
        "get_ingress(namespace='ingress-nginx')",
        "get_ingress(namespace='production')",
    ],
)
class GetIngressTool(BaseOpTool):
    """获取 Ingress 列表工具"""

    def __init__(self, db=None):  # type: ignore[no-untyped-def]
        self.k8s_client = init_k8s_client(db)

    async def execute(  # type: ignore[no-untyped-def]
        self,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        log_tool_start("get_ingress", namespace=namespace)
        try:
            ingresses = self.k8s_client.networking_v1.list_namespaced_ingress(namespace=namespace)

            data = [
                {
                    "name": ingress.metadata.name,
                    "namespace": ingress.metadata.namespace,
                    "hosts": [
                        rule.host
                        for rule in (ingress.spec.rules or [])
                        if rule.host
                    ],
                    "paths": [
                        {
                            "host": rule.host,
                            "path": path.path,
                            "backend_service": path.backend.service.name
                            if path.backend and path.backend.service
                            else None,
                        }
                        for rule in (ingress.spec.rules or [])
                        for path in (rule.http.paths if rule.http else [])
                    ],
                    "tls_hosts": [
                        tls.host
                        for tls in (ingress.spec.tls or [])
                        for host in tls.hosts
                    ],
                }
                for ingress in ingresses.items
            ]

            log_tool_success("get_ingress", len(data))
            return await tool_success_response(data, "get_ingress", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_ingress",
                context={"namespace": namespace}
            )


__all__ = [
    "GetServicesTool",
    "GetIngressTool",
]
