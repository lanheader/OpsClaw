"""
K8s Workload 读操作工具

包含 Deployment、StatefulSet、DaemonSet 相关的查询工具：
- GetDeploymentsTool: 获取 Deployment 列表
- GetStatefulSetsTool: 获取 StatefulSet 列表
- GetDaemonSetsTool: 获取 DaemonSet 列表
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
    description="获取 Kubernetes Deployment 列表",
    examples=[
        "get_deployments(namespace='default')",
        "get_deployments(namespace='kube-system')",
    ],
)
class GetDeploymentsTool(BaseOpTool):
    """获取 Deployment 列表工具"""

    def __init__(self, db=None):  # type: ignore[no-untyped-def]
        self.k8s_client = init_k8s_client(db)

    async def execute(  # type: ignore[no-untyped-def]
        self,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        log_tool_start("get_deployments", namespace=namespace)
        try:
            deployments = self.k8s_client.apps_v1.list_namespaced_deployment(namespace=namespace)

            data = [
                {
                    "name": deployment.metadata.name,
                    "namespace": deployment.metadata.namespace,
                    "replicas": deployment.spec.replicas,
                    "available_replicas": (
                        deployment.status.available_replicas
                        if deployment.status.available_replicas
                        else 0
                    ),
                    "ready": (
                        deployment.status.available_replicas == deployment.spec.replicas
                        if deployment.spec.replicas
                        else True
                    ),
                }
                for deployment in deployments.items
            ]

            log_tool_success("get_deployments", len(data))
            return tool_success_response(data, "get_deployments", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_deployments",
                context={"namespace": namespace}
            )


@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 Kubernetes StatefulSet 列表",
    examples=[
        "get_statefulsets(namespace='default')",
        "get_statefulsets(namespace='production')",
    ],
)
class GetStatefulSetsTool(BaseOpTool):
    """获取 StatefulSet 列表工具"""

    def __init__(self, db=None):  # type: ignore[no-untyped-def]
        self.k8s_client = init_k8s_client(db)

    async def execute(  # type: ignore[no-untyped-def]
        self,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        log_tool_start("get_statefulsets", namespace=namespace)
        try:
            statefulsets = self.k8s_client.apps_v1.list_namespaced_stateful_set(namespace=namespace)

            data = [
                {
                    "name": sts.metadata.name,
                    "namespace": sts.metadata.namespace,
                    "replicas": sts.spec.replicas,
                    "ready_replicas": (
                        sts.status.ready_replicas
                        if sts.status.ready_replicas
                        else 0
                    ),
                    "current_replicas": (
                        sts.status.current_replicas
                        if sts.status.current_replicas
                        else 0
                    ),
                    "service_name": sts.spec.service_name,
                }
                for sts in statefulsets.items
            ]

            log_tool_success("get_statefulsets", len(data))
            return tool_success_response(data, "get_statefulsets", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_statefulsets",
                context={"namespace": namespace}
            )


@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 Kubernetes DaemonSet 列表",
    examples=[
        "get_daemonsets(namespace='kube-system')",
        "get_daemonsets(namespace='monitoring')",
    ],
)
class GetDaemonSetsTool(BaseOpTool):
    """获取 DaemonSet 列表工具"""

    def __init__(self, db=None):  # type: ignore[no-untyped-def]
        self.k8s_client = init_k8s_client(db)

    async def execute(  # type: ignore[no-untyped-def]
        self,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        log_tool_start("get_daemonsets", namespace=namespace)
        try:
            daemonsets = self.k8s_client.apps_v1.list_namespaced_daemon_set(namespace=namespace)

            data = [
                {
                    "name": ds.metadata.name,
                    "namespace": ds.metadata.namespace,
                    "current_number_scheduled": (
                        ds.status.current_number_scheduled
                        if ds.status.current_number_scheduled
                        else 0
                    ),
                    "desired_number_scheduled": ds.spec.desired_number_scheduled,
                    "number_ready": (
                        ds.status.number_ready
                        if ds.status.number_ready
                        else 0
                    ),
                    "number_misscheduled": (
                        ds.status.number_misscheduled
                        if ds.status.number_misscheduled
                        else 0
                    ),
                }
                for ds in daemonsets.items
            ]

            log_tool_success("get_daemonsets", len(data))
            return tool_success_response(data, "get_daemonsets", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_daemonsets",
                context={"namespace": namespace}
            )


__all__ = [
    "GetDeploymentsTool",
    "GetStatefulSetsTool",
    "GetDaemonSetsTool",
]
