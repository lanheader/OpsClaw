"""
K8s 读操作工具（新架构）

使用 BaseOpTool 基类和 @register_tool 装饰器。
直接使用 Kubernetes SDK，不使用 CLI 降级。
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from app.integrations.kubernetes.client import create_client

from app.tools.base import (
    BaseOpTool,
    register_tool,
    OperationType,
    RiskLevel,
    ToolCategory,
    tool_error_response,
    tool_success_response,
)
from app.utils.logger import get_logger, get_request_context

logger = get_logger(__name__)


# 通用初始化函数
def _init_k8s_client(db=None):
    """初始化 K8s 客户端"""
    return create_client(db)


def _log_tool_start(tool_name: str, **kwargs):
    """记录工具开始执行的日志"""
    ctx = get_request_context()
    session_id = ctx.get('session_id', 'no-sess')
    params = {k: v for k, v in kwargs.items() if v is not None}
    logger.info(f"🔧 [{session_id}] 执行工具: {tool_name} | 参数: {params}")


def _log_tool_success(tool_name: str, result_count: int = None):
    """记录工具执行成功的日志"""
    ctx = get_request_context()
    session_id = ctx.get('session_id', 'no-sess')
    if result_count is not None:
        logger.info(f"✅ [{session_id}] 工具完成: {tool_name} | 返回 {result_count} 条记录")
    else:
        logger.info(f"✅ [{session_id}] 工具完成: {tool_name}")


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

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        namespace: str = "default",
        label_selector: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("get_pods", namespace=namespace, label_selector=label_selector)
        try:
            pods = self.k8s_client.core_v1.list_namespaced_pod(
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

            _log_tool_success("get_pods", len(data))
            return tool_success_response(data, "get_pods", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_pods",
                context={"namespace": namespace, "label_selector": label_selector}
            )

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

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        name: str,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("get_pod", name=name, namespace=namespace)
        try:
            pod = self.k8s_client.core_v1.read_namespaced_pod(name=name, namespace=namespace)

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

            _log_tool_success("get_pod")
            return tool_success_response(data, "get_pod", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_pod",
                context={"name": name, "namespace": namespace},
                suggestion=f"请先使用 get_pods 工具查看命名空间 '{namespace}' 中的 Pod 列表"
            )

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

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        name: str,
        namespace: str = "default",
        tail_lines: int = 100,
        container: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("get_pod_logs", name=name, namespace=namespace, tail_lines=tail_lines)
        try:
            logs = self.k8s_client.core_v1.read_namespaced_pod_log(
                name=name,
                namespace=namespace,
                tail_lines=tail_lines,
                container=container
            )

            log_lines = logs.split('\n') if logs else []
            data = {
                "logs": log_lines,
                "total_lines": len(log_lines),
                "tail_lines": tail_lines,
            }

            _log_tool_success("get_pod_logs", len(log_lines))
            return tool_success_response(data, "get_pod_logs", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_pod_logs",
                context={"name": name, "namespace": namespace},
                suggestion=f"请确认 Pod '{name}' 存在且正在运行"
            )


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

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        name: str,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("get_pod_events", name=name, namespace=namespace)
        try:
            field_selector = f"involvedObject.name={name}"
            events = self.k8s_client.core_v1.list_namespaced_event(
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

            _log_tool_success("get_pod_events", len(data))
            return tool_success_response(data, "get_pod_events", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_pod_events",
                context={"name": name, "namespace": namespace}
            )


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

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("get_deployments", namespace=namespace)
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

            _log_tool_success("get_deployments", len(data))
            return tool_success_response(data, "get_deployments", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_deployments",
                context={"namespace": namespace}
            )


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

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("get_services", namespace=namespace)
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

            _log_tool_success("get_services", len(data))
            return tool_success_response(data, "get_services", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_services",
                context={"namespace": namespace}
            )


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

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("get_nodes")
        try:
            nodes = self.k8s_client.core_v1.list_node()

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

            _log_tool_success("get_nodes", len(data))
            return tool_success_response(data, "get_nodes", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(e, "get_nodes")


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

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("get_namespaces")
        try:
            namespaces = self.k8s_client.core_v1.list_namespace()

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

            _log_tool_success("get_namespaces", len(data))
            return tool_success_response(data, "get_namespaces", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(e, "get_namespaces")


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

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        namespace: str = "default",
        field_selector: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("get_events", namespace=namespace, field_selector=field_selector)
        try:
            events = self.k8s_client.core_v1.list_namespaced_event(
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

            _log_tool_success("get_events", len(data))
            return tool_success_response(data, "get_events", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_events",
                context={"namespace": namespace, "field_selector": field_selector}
            )


# ==================== ConfigMap 操作 ====================

@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 Kubernetes ConfigMap 列表",
    examples=[
        "get_config_maps(namespace='default')",
        "get_config_maps(namespace='ka-baseline-tms')",
    ],
)
class GetConfigMapsTool(BaseOpTool):
    """获取 ConfigMap 列表工具"""

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("get_configmaps", namespace=namespace)
        try:
            configmaps = self.k8s_client.core_v1.list_namespaced_config_map(namespace=namespace)

            data = [
                {
                    "name": cm.metadata.name,
                    "namespace": cm.metadata.namespace,
                    "keys": list(cm.data.keys()) if cm.data else [],
                    "created": cm.metadata.creation_timestamp.isoformat()
                    if cm.metadata.creation_timestamp
                    else None,
                }
                for cm in configmaps.items
            ]

            _log_tool_success("get_configmaps", len(data))
            return tool_success_response(data, "get_configmaps", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_configmaps",
                context={"namespace": namespace}
            )


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
    "GetConfigMapsTool",
    "GetSecretsTool",
    "GetStatefulSetsTool",
    "GetDaemonSetsTool",
    "GetIngressTool",
    "GetPVsTool",
    "GetPVCsTool",
    "GetResourceQuotasTool",
    "DescribePodTool",
    "DescribeNodeTool",
]


# ==================== Secret 操作 ====================

@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.MEDIUM,
    permissions=["k8s.view"],
    description="获取 Kubernetes Secret 列表",
    examples=[
        "get_secrets(namespace='default')",
        "get_secrets(namespace='kube-system')",
    ],
)
class GetSecretsTool(BaseOpTool):
    """获取 Secret 列表工具（敏感信息，需谨慎）"""

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("get_secrets", namespace=namespace)
        try:
            secrets = self.k8s_client.core_v1.list_namespaced_secret(namespace=namespace)

            data = [
                {
                    "name": secret.metadata.name,
                    "namespace": secret.metadata.namespace,
                    "type": secret.type,
                    "keys": list(secret.data.keys()) if secret.data else [],
                    "created": secret.metadata.creation_timestamp.isoformat()
                    if secret.metadata.creation_timestamp
                    else None,
                }
                for secret in secrets.items
            ]

            _log_tool_success("get_secrets", len(data))
            return tool_success_response(data, "get_secrets", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_secrets",
                context={"namespace": namespace}
            )


# ==================== StatefulSet 操作 ====================

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

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("get_statefulsets", namespace=namespace)
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

            _log_tool_success("get_statefulsets", len(data))
            return tool_success_response(data, "get_statefulsets", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_statefulsets",
                context={"namespace": namespace}
            )


# ==================== DaemonSet 操作 ====================

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

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("get_daemonsets", namespace=namespace)
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

            _log_tool_success("get_daemonsets", len(data))
            return tool_success_response(data, "get_daemonsets", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_daemonsets",
                context={"namespace": namespace}
            )


# ==================== Ingress 操作 ====================

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

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("get_ingress", namespace=namespace)
        try:
            # 尝试使用 networking.k8s.io/v1 API
            try:
                ingresses = self.k8s_client.networking_v1.list_namespaced_ingress(namespace=namespace)
            except AttributeError:
                # 降级到 extensions/v1beta1 API
                ingresses = self.k8s_client.extensions_v1beta1.list_namespaced_ingress(namespace=namespace)

            data = [
                {
                    "name": ing.metadata.name,
                    "namespace": ing.metadata.namespace,
                    "hosts": [
                        host.host for host in (ing.spec.rules or [])
                        for host in (host.host or [])
                    ],
                    "class_name": ing.metadata.annotations.get("nginx.ingress.kubernetes.io/ingress.class", ""),
                    "created": ing.metadata.creation_timestamp.isoformat()
                    if ing.metadata.creation_timestamp
                    else None,
                }
                for ing in ingresses.items
            ]

            _log_tool_success("get_ingress", len(data))
            return tool_success_response(data, "get_ingress", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_ingress",
                context={"namespace": namespace},
                suggestion="请确认集群中安装了 Ingress Controller"
            )


# ==================== PV 操作 ====================

@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 PersistentVolume 列表",
    examples=[
        "get_pvs()",
    ],
)
class GetPVsTool(BaseOpTool):
    """获取 PersistentVolume 列表工具"""

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("get_pvs")
        try:
            pvs = self.k8s_client.core_v1.list_persistent_volume()

            data = [
                {
                    "name": pv.metadata.name,
                    "capacity": pv.spec.capacity.get("storage", ""),
                    "access_modes": pv.spec.access_modes or [],
                    "persistent_volume_ref": pv.spec.persistent_volume_ref,
                    "status": pv.status.phase,
                    "reason": pv.status.reason,
                }
                for pv in pvs.items
            ]

            _log_tool_success("get_pvs", len(data))
            return tool_success_response(data, "get_pvs", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(e, "get_pvs")


# ==================== PVC 操作 ====================

@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 PersistentVolumeClaim 列表",
    examples=[
        "get_pvcs(namespace='default')",
        "get_pvcs(namespace='production')",
    ],
)
class GetPVCsTool(BaseOpTool):
    """获取 PersistentVolumeClaim 列表工具"""

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("get_pvcs", namespace=namespace)
        try:
            pvcs = self.k8s_client.core_v1.list_namespaced_persistent_volume_claim(namespace=namespace)

            data = [
                {
                    "name": pvc.metadata.name,
                    "namespace": pvc.metadata.namespace,
                    "status": pvc.status.phase,
                    "capacity": pvc.spec.resources.requests.get("storage", ""),
                    "access_modes": pvc.spec.access_modes or [],
                    "volume_name": pvc.spec.volume_name,
                }
                for pvc in pvcs.items
            ]

            _log_tool_success("get_pvcs", len(data))
            return tool_success_response(data, "get_pvcs", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_pvcs",
                context={"namespace": namespace}
            )


# ==================== ResourceQuota 操作 ====================

@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 ResourceQuota 列表",
    examples=[
        "get_resourcequotas(namespace='default')",
    ],
)
class GetResourceQuotasTool(BaseOpTool):
    """获取 ResourceQuota 列表工具"""

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("get_resourcequotas", namespace=namespace)
        try:
            quotas = self.k8s_client.core_v1.list_namespaced_resource_quota(namespace=namespace)

            data = [
                {
                    "name": quota.metadata.name,
                    "namespace": quota.metadata.namespace,
                    "created": quota.metadata.creation_timestamp.isoformat()
                    if quota.metadata.creation_timestamp
                    else None,
                    "scopes": quota.spec.scopes or [],
                    "hard": {
                        resource: str(limit) if limit else "0"
                        for resource, limit in (quota.spec.hard or {}).items()
                    },
                    "used": {
                        resource: str(used) if used else "0"
                        for resource, used in (quota.status.used or {}).items()
                    },
                }
                for quota in quotas.items
            ]

            _log_tool_success("get_resourcequotas", len(data))
            return tool_success_response(data, "get_resourcequotas", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_resourcequotas",
                context={"namespace": namespace}
            )


# ==================== Describe 操作 ====================

@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 Pod 详细描述信息（类似 kubectl describe pod）",
    examples=[
        "describe_pod(name='nginx-pod', namespace='default')",
        "describe_pod(name='my-app-abc123', namespace='production')",
    ],
)
class DescribePodTool(BaseOpTool):
    """
    获取 Pod 详细描述信息工具

    提供类似于 `kubectl describe pod` 的详细信息，包括：
    - 状态信息
    - 容器状态
    - 最近事件
    - 资源使用
    """

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        name: str,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("describe_pod", name=name, namespace=namespace)
        try:
            # 获取 Pod 详情
            pod = self.k8s_client.core_v1.read_namespaced_pod(name=name, namespace=namespace)

            # 获取 Pod 事件
            field_selector = f"involvedObject.name={name}"
            events = self.k8s_client.core_v1.list_namespaced_event(
                namespace=namespace,
                field_selector=field_selector
            )

            # 构建详细描述信息
            data = {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "labels": pod.metadata.labels or {},
                "annotations": pod.metadata.annotations or {},
                "creation_timestamp": pod.metadata.creation_timestamp.isoformat()
                if pod.metadata.creation_timestamp
                else None,
                "phase": pod.status.phase,
                "conditions": [
                    {
                        "type": condition.type,
                        "status": condition.status,
                        "reason": condition.reason,
                        "message": condition.message,
                        "last_transition_time": condition.last_transition_time.isoformat()
                        if condition.last_transition_time
                        else None,
                    }
                    for condition in (pod.status.conditions or [])
                ],
                "containers": [],
                "init_containers": [],
                "volumes": [],
                "node": pod.spec.node_name,
                "service_account_name": pod.spec.service_account_name,
                "restart_policy": pod.spec.restart_policy,
                "qos_class": pod.status.qos_class,
                "events": [
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
                    for event in events.items[:10]  # 只取最近 10 个事件
                ],
            }

            # 处理容器信息
            for container in (pod.spec.containers or []):
                container_info = {
                    "name": container.name,
                    "image": container.image,
                    "image_pull_policy": container.image_pull_policy,
                    "ports": [
                        {
                            "name": port.name,
                            "container_port": port.container_port,
                            "protocol": port.protocol,
                        }
                        for port in (container.ports or [])
                    ],
                    "resources": {
                        "limits": container.resources.limits or {},
                        "requests": container.resources.requests or {},
                    }
                }

                # 获取容器状态
                for status in (pod.status.container_statuses or []):
                    if status.name == container.name:
                        container_info["state"] = {
                            "state": status.state,
                            "running": {
                                "started_at": status.running.started_at.isoformat()
                                if status.running and status.running.started_at
                                else None,
                            }
                            if status.running else {},
                            "terminated": {
                                "exit_code": status.terminated.exit_code,
                                "finished_at": status.terminated.finished_at.isoformat()
                                if status.terminated and status.terminated.finished_at
                                else None,
                                "reason": status.terminated.reason,
                                "message": status.terminated.message,
                            }
                            if status.terminated else {},
                            "waiting": {
                                "reason": status.waiting.reason,
                                "message": status.waiting.message,
                            }
                            if status.waiting else {},
                        }
                        if status.state == "running":
                            container_info["ready"] = status.ready
                        container_info["restart_count"] = status.restart_count
                        break

                data["containers"].append(container_info)

            # 处理 init 容器
            for container in (pod.spec.init_containers or []):
                container_info = {
                    "name": container.name,
                    "image": container.image,
                    "resources": {
                        "limits": container.resources.limits or {},
                        "requests": container.resources.requests or {},
                    }
                }
                data["init_containers"].append(container_info)

            # 处理卷
            for volume in (pod.spec.volumes or []):
                volume_info = {"name": volume.name}
                if volume.secret:
                    volume_info["secret"] = volume.secret.secret_name
                elif volume.config_map:
                    volume_info["config_map"] = volume.config_map.name
                elif volume.persistent_volume_claim:
                    volume_info["pvc"] = volume.persistent_volume_claim.claim_name
                elif volume.empty_dir:
                    volume_info["empty_dir"] = {}
                elif volume.host_path:
                    volume_info["host_path"] = volume.host_path.path
                data["volumes"].append(volume_info)

            _log_tool_success("describe_pod")
            return tool_success_response(data, "describe_pod", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "describe_pod",
                context={"name": name, "namespace": namespace},
                suggestion=f"请确认 Pod '{name}' 存在于命名空间 '{namespace}'"
            )


@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 Node 详细描述信息（类似 kubectl describe node）",
    examples=[
        "describe_node(name='node-1')",
        "describe_node(name='node-2')",
    ],
)
class DescribeNodeTool(BaseOpTool):
    """
    获取 Node 详细描述信息工具

    提供类似于 `kubectl describe node` 的详细信息，包括：
    - 状态信息
    - 资源容量
    - 条件
    - Pod 列表
    """

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("describe_node", name=name)
        try:
            node = self.k8s_client.core_v1.read_node(name=name)

            # 获取节点上的 Pod
            field_selector = f"spec.nodeName={name}"
            pods = self.k8s_client.core_v1.list_pod_for_all_namespaces(field_selector=field_selector)

            data = {
                "name": node.metadata.name,
                "labels": node.metadata.labels or {},
                "annotations": node.metadata.annotations or {},
                "creation_timestamp": node.metadata.creation_timestamp.isoformat()
                if node.metadata.creation_timestamp
                else None,
                "conditions": [
                    {
                        "type": condition.type,
                        "status": condition.status,
                        "reason": condition.reason,
                        "message": condition.message,
                        "last_transition_time": condition.last_transition_time.isoformat()
                        if condition.last_transition_time
                        else None,
                    }
                    for condition in (node.status.conditions or [])
                ],
                "capacity": node.status.capacity or {},
                "allocatable": node.status.allocatable or {},
                "status": {
                    "phase": node.status.phase if node.status.phase else "Unknown",
                    "addresses": node.status.addresses or [],
                },
                "unschedulable": node.spec.unschedulable or False,
                "info": node.status.node_info or {},
                "pods": [
                    {
                        "name": pod.metadata.name,
                        "namespace": pod.metadata.namespace,
                        "phase": pod.status.phase,
                    }
                    for pod in pods.items[:50]  # 限制最多 50 个 Pod
                ],
            }

            _log_tool_success("describe_node")
            return tool_success_response(data, "describe_node", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "describe_node",
                context={"name": name},
                suggestion=f"请确认节点 '{name}' 存在"
            )
