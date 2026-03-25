"""
K8s 读操作工具（新架构）

使用 BaseOpTool 基类和 @register_tool 装饰器。
直接使用 Kubernetes SDK，不使用 CLI 降级。
"""

from typing import Dict, Any, Optional

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
]
