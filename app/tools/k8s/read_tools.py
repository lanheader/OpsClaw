"""
K8s 读操作工具（新架构）

使用 BaseOpTool 基类和 @register_tool 装饰器。
支持 SDK → CLI 降级机制。
"""

from typing import Dict, Any, Optional
import logging

from app.tools.base import (
    BaseOpTool,
    register_tool,
    OperationType,
    RiskLevel,
    ToolCategory,
)
from app.tools.fallback import get_k8s_fallback

logger = logging.getLogger(__name__)


# ==================== Pod 操作 ====================

@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 Kubernetes Pod 列表",
    examples=[
        "get_pods(namespace='default')",
        "get_pods(namespace='production', label_selector='app=api')",
    ],
)
class GetPodsTool(BaseOpTool):
    """
    获取 Pod 列表工具

    查询指定命名空间下的所有 Pod，支持标签过滤。
    """

    def __init__(self):
        from app.integrations.kubernetes.client import K8sClient
        self.k8s_client = K8sClient()
        self.fallback = get_k8s_fallback()

    async def execute(
        self,
        namespace: str = "default",
        label_selector: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        try:
            logger.info(f"Using K8s SDK to list pods in {namespace}")
            result = await self._execute_with_sdk(namespace, label_selector)
            return result
        except Exception as e:
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="get pods",
                namespace=namespace,
                label_selector=label_selector
            )
            return result

    async def _execute_with_sdk(
        self,
        namespace: str,
        label_selector: Optional[str] = None,
    ) -> Dict[str, Any]:
        """使用 SDK 执行"""
        pods = await self.k8s_client.list_namespaced_pod(
            namespace=namespace,
            label_selector=label_selector
        )

        data = [
            {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "phase": pod.status.phase,
                "ready": self._is_pod_ready(pod),
                "restarts": sum(
                    container.restart_count
                    for container in (pod.status.container_statuses or [])
                ),
                "created": pod.metadata.creation_timestamp.isoformat()
                if pod.metadata.creation_timestamp
                else None,
                "node": pod.spec.node_name,
            }
            for pod in pods.items
        ]

        return {
            "success": True,
            "data": data,
            "execution_mode": "sdk",
            "source": "kubernetes-sdk",
        }

    def _is_pod_ready(self, pod) -> bool:
        """检查 Pod 是否就绪"""
        if not pod.status.container_statuses:
            return False
        return all(cs.ready for cs in pod.status.container_statuses)


@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取单个 Pod 详情",
    examples=[
        "get_pod(name='nginx-pod', namespace='default')",
    ],
)
class GetPodTool(BaseOpTool):
    """获取单个 Pod 详情工具"""

    def __init__(self):
        from app.integrations.kubernetes.client import K8sClient
        self.k8s_client = K8sClient()
        self.fallback = get_k8s_fallback()

    async def execute(
        self,
        name: str,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        try:
            logger.info(f"Using K8s SDK to get pod {name}")
            result = await self._execute_with_sdk(name, namespace)
            return result
        except Exception as e:
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="get pod",
                name=name,
                namespace=namespace
            )
            return result

    async def _execute_with_sdk(self, name: str, namespace: str) -> Dict[str, Any]:
        """使用 SDK 执行"""
        pod = await self.k8s_client.read_namespaced_pod(name, namespace)

        data = {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "phase": pod.status.phase,
            "ready": self._is_pod_ready(pod),
            "restarts": sum(
                container.restart_count
                for container in (pod.status.container_statuses or [])
            ),
            "created": pod.metadata.creation_timestamp.isoformat()
            if pod.metadata.creation_timestamp
            else None,
            "node": pod.spec.node_name,
            "labels": pod.metadata.labels or {},
            "annotations": pod.metadata.annotations or {},
        }

        return {
            "success": True,
            "data": data,
            "execution_mode": "sdk",
            "source": "kubernetes-sdk",
        }

    def _is_pod_ready(self, pod) -> bool:
        """检查 Pod 是否就绪"""
        if not pod.status.container_statuses:
            return False
        return all(cs.ready for cs in pod.status.container_statuses)


@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 Pod 日志",
    examples=[
        "get_pod_logs(name='nginx-pod', namespace='default')",
        "get_pod_logs(name='nginx-pod', tail_lines=50)",
    ],
)
class GetPodLogsTool(BaseOpTool):
    """获取 Pod 日志工具"""

    def __init__(self):
        from app.integrations.kubernetes.client import K8sClient
        self.k8s_client = K8sClient()
        self.fallback = get_k8s_fallback()

    async def execute(
        self,
        name: str,
        namespace: str = "default",
        tail_lines: int = 100,
        container: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        try:
            logger.info(f"Using K8s SDK to get logs for pod {name}")
            result = await self._execute_with_sdk(name, namespace, tail_lines, container)
            return result
        except Exception as e:
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            container_arg = f"-c {container}" if container else ""
            result = await self.fallback.execute(
                operation=f"logs {container_arg}".strip(),
                name=name,
                namespace=namespace,
                tail_lines=tail_lines
            )
            return result

    async def _execute_with_sdk(
        self,
        name: str,
        namespace: str,
        tail_lines: int,
        container: Optional[str],
    ) -> Dict[str, Any]:
        """使用 SDK 执行"""
        logs = await self.k8s_client.read_namespaced_pod_log(
            name=name,
            namespace=namespace,
            tail_lines=tail_lines,
            container=container
        )

        log_lines = logs.split('\n') if logs else []

        return {
            "success": True,
            "data": {
                "logs": log_lines,
                "total_lines": len(log_lines),
                "tail_lines": tail_lines,
            },
            "execution_mode": "sdk",
            "source": "kubernetes-sdk",
        }


@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 Pod 事件",
    examples=[
        "get_pod_events(name='nginx-pod', namespace='default')",
    ],
)
class GetPodEventsTool(BaseOpTool):
    """获取 Pod 事件工具"""

    def __init__(self):
        from app.integrations.kubernetes.client import K8sClient
        self.k8s_client = K8sClient()
        self.fallback = get_k8s_fallback()

    async def execute(
        self,
        name: str,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        try:
            logger.info(f"Using K8s SDK to get events for pod {name}")
            field_selector = f"involvedObject.name={name}"
            result = await self._execute_with_sdk(namespace, field_selector)
            return result
        except Exception as e:
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="get events",
                namespace=namespace,
                field_selector=f"involvedObject.name={name}"
            )
            return result

    async def _execute_with_sdk(
        self,
        namespace: str,
        field_selector: str,
    ) -> Dict[str, Any]:
        """使用 SDK 执行"""
        events = await self.k8s_client.list_namespaced_event(
            namespace=namespace,
            field_selector=field_selector
        )

        data = [
            {
                "type": event.type,
                "reason": event.reason,
                "message": event.message,
                "first_timestamp": event.first_timestamp.isoformat()
                if event.first_timestamp
                else None,
                "last_timestamp": event.last_timestamp.isoformat()
                if event.last_timestamp
                else None,
                "count": event.count,
            }
            for event in events.items
        ]

        return {
            "success": True,
            "data": data,
            "execution_mode": "sdk",
            "source": "kubernetes-sdk",
        }


# ==================== Deployment 操作 ====================

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

    def __init__(self):
        from app.integrations.kubernetes.client import K8sClient
        self.k8s_client = K8sClient()
        self.fallback = get_k8s_fallback()

    async def execute(
        self,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        try:
            logger.info(f"Using K8s SDK to list deployments in {namespace}")
            deployments = await self.k8s_client.list_namespaced_deployment(namespace)

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

            return {
                "success": True,
                "data": data,
                "execution_mode": "sdk",
                "source": "kubernetes-sdk",
            }
        except Exception as e:
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="get deployments",
                namespace=namespace
            )
            return result


# ==================== Service 操作 ====================

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

    def __init__(self):
        from app.integrations.kubernetes.client import K8sClient
        self.k8s_client = K8sClient()
        self.fallback = get_k8s_fallback()

    async def execute(
        self,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        try:
            logger.info(f"Using K8s SDK to list services in {namespace}")
            services = await self.k8s_client.list_namespaced_service(namespace)

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

            return {
                "success": True,
                "data": data,
                "execution_mode": "sdk",
                "source": "kubernetes-sdk",
            }
        except Exception as e:
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="get services",
                namespace=namespace
            )
            return result


# ==================== Node 操作 ====================

@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 Kubernetes Node 列表",
    examples=[
        "get_nodes()",
    ],
)
class GetNodesTool(BaseOpTool):
    """获取 Node 列表工具"""

    def __init__(self):
        from app.integrations.kubernetes.client import K8sClient
        self.k8s_client = K8sClient()
        self.fallback = get_k8s_fallback()

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行工具操作"""
        try:
            logger.info("Using K8s SDK to list nodes")
            nodes = await self.k8s_client.list_node()

            data = [
                {
                    "name": node.metadata.name,
                    "ready": all(
                        condition.status == "True"
                        for condition in node.status.conditions
                        if condition.type == "Ready"
                    ),
                    "unschedulable": node.spec.unschedulable or False,
                    "capacity": {
                        "cpu": node.status.capacity.get("cpu"),
                        "memory": node.status.capacity.get("memory"),
                        "pods": node.status.capacity.get("pods"),
                    }
                    if node.status.capacity
                    else {},
                    "labels": node.metadata.labels or {},
                }
                for node in nodes.items
            ]

            return {
                "success": True,
                "data": data,
                "execution_mode": "sdk",
                "source": "kubernetes-sdk",
            }
        except Exception as e:
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(operation="get nodes")
            return result


# ==================== Namespace 操作 ====================

@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 Kubernetes Namespace 列表",
    examples=[
        "get_namespaces()",
    ],
)
class GetNamespacesTool(BaseOpTool):
    """获取 Namespace 列表工具"""

    def __init__(self):
        from app.integrations.kubernetes.client import K8sClient
        self.k8s_client = K8sClient()
        self.fallback = get_k8s_fallback()

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行工具操作"""
        try:
            logger.info("Using K8s SDK to list namespaces")
            namespaces = await self.k8s_client.list_namespace()

            data = [
                {
                    "name": ns.metadata.name,
                    "status": ns.status.phase,
                    "created": ns.metadata.creation_timestamp.isoformat()
                    if ns.metadata.creation_timestamp
                    else None,
                    "labels": ns.metadata.labels or {},
                }
                for ns in namespaces.items
            ]

            return {
                "success": True,
                "data": data,
                "execution_mode": "sdk",
                "source": "kubernetes-sdk",
            }
        except Exception as e:
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(operation="get namespaces")
            return result


# ==================== Event 操作 ====================

@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 Kubernetes Event 列表",
    examples=[
        "get_events(namespace='default')",
        "get_events(namespace='default', field_selector='type=Warning')",
    ],
)
class GetEventsTool(BaseOpTool):
    """获取 Event 列表工具"""

    def __init__(self):
        from app.integrations.kubernetes.client import K8sClient
        self.k8s_client = K8sClient()
        self.fallback = get_k8s_fallback()

    async def execute(
        self,
        namespace: str = "default",
        field_selector: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        try:
            logger.info(f"Using K8s SDK to list events in {namespace}")
            events = await self.k8s_client.list_namespaced_event(
                namespace=namespace,
                field_selector=field_selector
            )

            data = [
                {
                    "type": event.type,
                    "reason": event.reason,
                    "message": event.message,
                    "involved_object": {
                        "kind": event.involved_object.kind if event.involved_object else None,
                        "name": event.involved_object.name if event.involved_object else None,
                    },
                    "first_timestamp": event.first_timestamp.isoformat()
                    if event.first_timestamp
                    else None,
                    "last_timestamp": event.last_timestamp.isoformat()
                    if event.last_timestamp
                    else None,
                    "count": event.count,
                }
                for event in events.items
            ]

            return {
                "success": True,
                "data": data,
                "execution_mode": "sdk",
                "source": "kubernetes-sdk",
            }
        except Exception as e:
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="get events",
                namespace=namespace,
                field_selector=field_selector
            )
            return result


__all__ = [
    "GetPodsTool",
    "GetPodTool",
    "GetPodLogsTool",
    "GetPodEventsTool",
    "GetDeploymentsTool",
    "GetServicesTool",
    "GetNodesTool",
    "GetNamespacesTool",
    "GetEventsTool",
]
