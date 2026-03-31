"""
K8s ConfigMap/Secret/PVC/Node 读操作工具

包含 ConfigMap、Secret、Pvc、 Node 相关的查询工具：
- GetConfigMapsTool: 查询 ConfigMap 列表
- GetSecretsTool: 获取 Secret 列表
- GetPVCsTool: 查询 PVC 详情
- GetNodesTool: 查询节点列表
- GetEventsTool: 查询集群事件
- GetResourceQuotasTool: 查询资源配额
- DescribeNodeTool: 获取节点详细描述
"""

from typing import Dict, Any, Optional

from app.tools.base import (
    BaseOpTool,
    register_tool,
    OperationType,
    RiskLevel,
    tool_success_response,
    tool_error_response,
)
from app.tools.k8s.common import (
    init_k8s_client,
    log_tool_start,
    log_tool_success,
    format_timestamp,
)
from app.utils.logger import get_logger, get_request_context
from app.integrations.kubernetes.client import create_client

logger = get_logger(__name__)


# ==================== ConfigMap ====================
@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 Kubernetes ConfigMap 列表",
    examples=[
        "get_configmaps(namespace='default')",
        "get_configmaps(namespace='kube-system')",
    ],
)
class GetConfigMapsTool(BaseOpTool):
    """获取 ConfigMap 列表工具"""

    def __init__(self, db=None):
        self.k8s_client = init_k8s_client(db)
        self.logger = get_logger(__name__)
        self.request_context = get_request_context()
        self.session_id = self.request_context.get('session_id', 'no-sess')

    async def execute(self, namespace: str = "default", **kwargs) -> Dict[str, Any]:
        """执行工具操作"""
        self.logger.info(
            f"🔧 [{self.session_id}] 执行工具: get_configmaps | namespace: {namespace}"
        )
        log_tool_start("get_configmaps", namespace=namespace)
        try:
            configmaps = self.k8s_client.core_v1.list_namespaced_config_map(namespace=namespace)
            data = [
                {
                    "name": cm.metadata.name,
                    "namespace": cm.metadata.namespace,
                    "data": cm.data,
                    "creation_timestamp": format_timestamp(cm.metadata.creation_timestamp),
                }
                for cm in configmaps.items
            ]
            log_tool_success("get_configmaps", len(data))
            return tool_success_response(data, "get_configmaps", source="kubernetes-sdk")
        except Exception as e:
            return tool_error_response(
                e, "get_configmaps",
                context={"namespace": namespace}
            )


# ==================== Secret ====================
@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 Kubernetes Secret 列表",
    examples=[
        "get_secrets(namespace='default')",
        "get_secrets(namespace='kube-system')",
    ],
)
class GetSecretsTool(BaseOpTool):
    """获取 Secret 列表工具"""

    def __init__(self, db=None):
        self.k8s_client = init_k8s_client(db)
        self.logger = get_logger(__name__)
        self.request_context = get_request_context()
        self.session_id = self.request_context.get('session_id', 'no-sess')

    async def execute(self, namespace: str = "default", **kwargs) -> Dict[str, Any]:
        """执行工具操作"""
        self.logger.info(
            f"🔧 [{self.session_id}] 执行工具: get_secrets | namespace: {namespace}"
        )
        log_tool_start("get_secrets", namespace=namespace)
        try:
            secrets = self.k8s_client.core_v1.list_namespaced_secret(namespace=namespace)
            data = [
                {
                    "name": secret.metadata.name,
                    "namespace": secret.metadata.namespace,
                    "type": secret.type,
                    "creation_timestamp": format_timestamp(secret.metadata.creation_timestamp),
                }
                for secret in secrets.items
            ]
            log_tool_success("get_secrets", len(data))
            return tool_success_response(data, "get_secrets", source="kubernetes-sdk")
        except Exception as e:
            return tool_error_response(
                e, "get_secrets",
                context={"namespace": namespace}
            )


# ==================== PVC ====================
@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 Kubernetes PVC 列表",
    examples=[
        "get_pvcs(namespace='default')",
        "get_pvcs(namespace='production')",
    ],
)
class GetPVCsTool(BaseOpTool):
    """获取 PVC 列表工具"""

    def __init__(self, db=None):
        self.k8s_client = init_k8s_client(db)
        self.logger = get_logger(__name__)
        self.request_context = get_request_context()
        self.session_id = self.request_context.get('session_id', 'no-sess')

    async def execute(self, namespace: str = "default", **kwargs) -> Dict[str, Any]:
        """执行工具操作"""
        self.logger.info(
            f"🔧 [{self.session_id}] 执行工具: get_pvcs | namespace: {namespace}"
        )
        log_tool_start("get_pvcs", namespace=namespace)
        try:
            pvcs = self.k8s_client.core_v1.list_namespaced_persistent_volume_claim(namespace=namespace)
            data = [
                {
                    "name": pvc.metadata.name,
                    "namespace": pvc.metadata.namespace,
                    "status": pvc.status.phase,
                    "capacity": pvc.spec.resources.requests.storage,
                    "access_modes": pvc.spec.access_modes,
                    "storage_class": pvc.spec.storage_class_name,
                }
                for pvc in pvcs.items
            ]
            log_tool_success("get_pvcs", len(data))
            return tool_success_response(data, "get_pvcs", source="kubernetes-sdk")
        except Exception as e:
            return tool_error_response(
                e, "get_pvcs",
                context={"namespace": namespace}
            )


# ==================== Node ====================
@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取 Kubernetes Node 列表",
    examples=[
        "get_nodes()",
        "get_nodes(label_selector='node-role.kubernetes.io/master')",
    ],
)
class GetNodesTool(BaseOpTool):
    """获取 Node 列表工具"""

    def __init__(self, db=None):
        self.k8s_client = init_k8s_client(db)
        self.logger = get_logger(__name__)
        self.request_context = get_request_context()
        self.session_id = self.request_context.get('session_id', 'no-sess')
    async def execute(self, label_selector: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """执行工具操作"""
        self.logger.info(
            f"🔧 [{self.session_id}] 执行工具: get_nodes | label_selector: {label_selector}"
        )
        log_tool_start("get_nodes", label_selector=label_selector)
        try:
            nodes = self.k8s_client.core_v1.list_node(label_selector=label_selector)
            data = [
                {
                    "name": node.metadata.name,
                    "status": [
                        {
                            "type": condition.type,
                            "status": condition.status,
                        }
                        for condition in node.status.conditions
                    ],
                    "roles": node.metadata.labels.get("node-role", []),
                    "addresses": [
                        addr.address
                        for addr in node.status.addresses
                    ],
                    "capacity": {
                        "cpu": node.status.capacity.cpu,
                        "memory": node.status.capacity.memory,
                        "pods": node.status.capacity.pods,
                    } if node.status.capacity else {},
                    "kubelet_version": node.status.node_info.kubelet_version,
                    "os_image": node.status.node_info.os_image,
                    "kernel_version": node.status.node_info.kernel_version,
                    "container_runtime_version": node.status.node_info.container_runtime_version,
                }
                for node in nodes.items
            ]
            log_tool_success("get_nodes", len(data))
            return tool_success_response(data, "get_nodes", source="kubernetes-sdk")
        except Exception as e:
            return tool_error_response(
                e, "get_nodes",
                context={"label_selector": label_selector}
            )


# ==================== Events ====================
@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取集群事件",
    examples=[
        "get_events(namespace='default')",
        "get_events(namespace='kube-system', limit=10)",
    ],
)
class GetEventsTool(BaseOpTool):
    """获取集群事件工具"""

    def __init__(self, db=None):
        self.k8s_client = init_k8s_client(db)
        self.logger = get_logger(__name__)
        self.request_context = get_request_context()
        self.session_id = self.request_context.get('session_id', 'no-sess')
    async def execute(self, namespace: str = "default", limit: int = 100, **kwargs) -> Dict[str, Any]:
        """执行工具操作"""
        self.logger.info(
            f"🔧 [{self.session_id}] 执行工具: get_events | namespace: {namespace}, limit={limit}"
        )
        log_tool_start("get_events", namespace=namespace, limit=limit)
        try:
            events = self.k8s_client.core_v1.list_namespaced_event(
                namespace=namespace,
                limit=limit
            )
            data = [
                {
                    "type": event.type,
                    "reason": event.reason,
                    "message": event.message,
                    "count": event.count,
                    "first_timestamp": format_timestamp(event.first_timestamp),
                    "last_timestamp": format_timestamp(event.last_timestamp),
                    "involved_object": event.involved_object.name
                    if event.involved_object
                    else None,
                }
                for event in events.items
            ]
            log_tool_success("get_events", len(data))
            return tool_success_response(data, "get_events", source="kubernetes-sdk")
        except Exception as e:
            return tool_error_response(
                e, "get_events",
                context={"namespace": namespace, "limit": limit}
            )


# ==================== ResourceQuota ====================
@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取资源配额列表",
    examples=[
        "get_resource_quotas(namespace='default')",
    ],
)
class GetResourceQuotasTool(BaseOpTool):
    """获取资源配额列表工具"""

    def __init__(self, db=None):
        self.k8s_client = init_k8s_client(db)
        self.logger = get_logger(__name__)
        self.request_context = get_request_context()
        self.session_id = self.request_context.get('session_id', 'no-sess')
    async def execute(self, namespace: str = "default", **kwargs) -> Dict[str, Any]:
        """执行工具操作"""
        self.logger.info(
            f"🔧 [{self.session_id}] 执行工具: get_resource_quotas | namespace: {namespace}"
        )
        log_tool_start("get_resource_quotas", namespace=namespace)
        try:
            quotas = self.k8s_client.core_v1.list_namespaced_resource_quota(namespace=namespace)
            data = [
                {
                    "name": quota.metadata.name,
                    "namespace": quota.metadata.namespace,
                    "status": {
                        "hard": quota.status.hard,
                        "used": quota.status.used,
                        "requests": quota.status.requests,
                        "limits": quota.status.limits
                    } if quota.status
                    else {},
                }
                for quota in quotas.items
            ]
            log_tool_success("get_resource_quotas", len(data))
            return tool_success_response(data, "get_resource_quotas", source="kubernetes-sdk")
        except Exception as e:
            return tool_error_response(
                e, "get_resource_quotas",
                context={"namespace": namespace}
            )


# ==================== DescribeNode ====================
@register_tool(
    group="k8s.read",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["k8s.view"],
    description="获取节点详细描述信息",
    examples=[
        "describe_node(name='node-name')",
    ],
)
class DescribeNodeTool(BaseOpTool):
    """获取节点详细描述信息工具"""

    def __init__(self, db=None):
        self.k8s_client = init_k8s_client(db)
        self.logger = get_logger(__name__)
        self.request_context = get_request_context()
        self.session_id = self.request_context.get('session_id', 'no-sess')
    async def execute(self, name: str, **kwargs) -> Dict[str, Any]:
        """执行工具操作"""
        self.logger.info(
            f"🔧 [{self.session_id}] 执行工具: describe_node | name={name}"
        )
        log_tool_start("describe_node", name=name)
        try:
            node = self.k8s_client.core_v1.read_node(name=name)
            # 获取节点上的 Pod 列表
            pods = self.k8s_client.core_v1.list_pod(
                field_selector=f"spec.nodeName={name}"
            )
            pods_info = []
            for pod in pods.items:
                pods_info.append({
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": pod.status.phase,
                    "ip": pod.status.pod_ip,
                    "containers": len(pod.spec.containers) if pod.spec.containers else 0,
                })
            data = {
                "node": {
                    "name": node.metadata.name,
                    "labels": node.metadata.labels or {},
                    "annotations": node.metadata.annotations or {},
                    "creation_timestamp": format_timestamp(node.metadata.creation_timestamp),
                    "status": {
                        "conditions": [
                            {
                                "type": condition.type,
                                "status": condition.status,
                            }
                            for condition in (node.status.conditions or [])
                        ],
                        "addresses": node.status.addresses,
                        "capacity": {
                            "cpu": node.status.capacity.cpu,
                            "memory": node.status.capacity.memory,
                            "pods": node.status.capacity.pods,
                        } if node.status.capacity else {},
                        "node_info": node.status.node_info,
                        "images": len(node.status.images) if node.status.images else 0,
                        "pods": pods_info,
                    }
                }
            }
            log_tool_success("describe_node")
            return tool_success_response(data, "describe_node", source="kubernetes-sdk")
        except Exception as e:
            return tool_error_response(
                e, "describe_node",
                context={"name": name},
                suggestion=f"请确认节点 '{name}' 存在"
            )


__all__ = [
    "GetConfigMapsTool",
    "GetSecretsTool",
    "GetPVCsTool",
    "GetNodesTool",
    "GetEventsTool",
    "GetResourceQuotasTool",
    "DescribeNodeTool",
]
