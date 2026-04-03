"""
K8s Pod 读操作工具

包含所有 Pod 相关的查询工具：
- GetPodsTool: 获取 Pod 列表
- GetPodTool: 获取单个 Pod 详情
- GetPodLogsTool: 获取 Pod 日志
- GetPodEventsTool: 获取 Pod 事件
- DescribePodTool: 获取 Pod 详细描述
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
    is_pod_ready,
    format_timestamp,
)


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
    """获取 Pod 列表工具"""

    def __init__(self, db=None):  # type: ignore[no-untyped-def]
        self.k8s_client = init_k8s_client(db)

    async def execute(  # type: ignore[no-untyped-def]
        self,
        namespace: str = "default",
        label_selector: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        log_tool_start("get_pods", namespace=namespace, label_selector=label_selector)
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
                    "ready": is_pod_ready(pod),
                    "restarts": sum(
                        container.restart_count
                        for container in (pod.status.container_statuses or [])
                    ),
                    "created": format_timestamp(pod.metadata.creation_timestamp),
                    "node": pod.spec.node_name,
                }
                for pod in pods.items
            ]

            log_tool_success("get_pods", len(data))
            return tool_success_response(data, "get_pods", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_pods",
                context={"namespace": namespace, "label_selector": label_selector}
            )


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

    def __init__(self, db=None):  # type: ignore[no-untyped-def]
        self.k8s_client = init_k8s_client(db)

    async def execute(  # type: ignore[no-untyped-def]
        self,
        name: str,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        log_tool_start("get_pod", name=name, namespace=namespace)
        try:
            pod = self.k8s_client.core_v1.read_namespaced_pod(name=name, namespace=namespace)

            data = {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "phase": pod.status.phase,
                "ready": is_pod_ready(pod),
                "restarts": sum(
                    container.restart_count
                    for container in (pod.status.container_statuses or [])
                ),
                "created": format_timestamp(pod.metadata.creation_timestamp),
                "node": pod.spec.node_name,
                "labels": pod.metadata.labels or {},
                "annotations": pod.metadata.annotations or {},
            }

            log_tool_success("get_pod")
            return tool_success_response(data, "get_pod", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_pod",
                context={"name": name, "namespace": namespace},
                suggestion=f"请先使用 get_pods 工具查看命名空间 '{namespace}' 中的 Pod 列表"
            )


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

    def __init__(self, db=None):  # type: ignore[no-untyped-def]
        self.k8s_client = init_k8s_client(db)

    async def execute(  # type: ignore[no-untyped-def]
        self,
        name: str,
        namespace: str = "default",
        tail_lines: int = 100,
        container: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        log_tool_start("get_pod_logs", name=name, namespace=namespace, tail_lines=tail_lines)
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

            log_tool_success("get_pod_logs", len(log_lines))
            return tool_success_response(data, "get_pod_logs", source="kubernetes-sdk")

        except Exception as e:
            error_msg = str(e)
            # 优化常见错误的提示
            if "400" in error_msg or "Bad Request" in error_msg:
                suggestion = f"Pod '{name}' 当前不支持日志读取，可能已终止或容器未正常运行。请先检查 Pod 状态。"
            elif "404" in error_msg or "Not Found" in error_msg:
                suggestion = f"Pod '{name}' 在命名空间 '{namespace}' 中不存在，请检查名称和命名空间。"
            else:
                suggestion = f"请确认 Pod '{name}' 存在且正在运行"
            return tool_error_response(
                e, "get_pod_logs",
                context={"name": name, "namespace": namespace},
                suggestion=suggestion
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

    def __init__(self, db=None):  # type: ignore[no-untyped-def]
        self.k8s_client = init_k8s_client(db)

    async def execute(  # type: ignore[no-untyped-def]
        self,
        name: str,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        log_tool_start("get_pod_events", name=name, namespace=namespace)
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
                    "first_timestamp": format_timestamp(event.first_timestamp),
                    "last_timestamp": format_timestamp(event.last_timestamp),
                    "count": event.count,
                }
                for event in events.items
            ]

            log_tool_success("get_pod_events", len(data))
            return tool_success_response(data, "get_pod_events", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "get_pod_events",
                context={"name": name, "namespace": namespace}
            )


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
    """获取 Pod 详细描述信息工具"""

    def __init__(self, db=None):  # type: ignore[no-untyped-def]
        self.k8s_client = init_k8s_client(db)

    async def execute(  # type: ignore[no-untyped-def]
        self,
        name: str,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        log_tool_start("describe_pod", name=name, namespace=namespace)
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
                "creation_timestamp": format_timestamp(pod.metadata.creation_timestamp),
                "phase": pod.status.phase,
                "conditions": [
                    {
                        "type": condition.type,
                        "status": condition.status,
                        "reason": condition.reason,
                        "message": condition.message,
                        "last_transition_time": format_timestamp(condition.last_transition_time),
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
                        "first_timestamp": format_timestamp(event.first_timestamp),
                        "last_timestamp": format_timestamp(event.last_timestamp),
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
                        s = status.state
                        container_info["state"] = {
                            "running": {
                                "started_at": format_timestamp(s.running.started_at)
                                if s and s.running else None,
                            } if s and s.running else {},
                            "terminated": {
                                "exit_code": s.terminated.exit_code,
                                "finished_at": format_timestamp(s.terminated.finished_at),
                                "reason": s.terminated.reason,
                                "message": s.terminated.message,
                            } if s and s.terminated else {},
                            "waiting": {
                                "reason": s.waiting.reason,
                                "message": s.waiting.message,
                            } if s and s.waiting else {},
                        }
                        if s and s.running:
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

            log_tool_success("describe_pod")
            return tool_success_response(data, "describe_pod", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "describe_pod",
                context={"name": name, "namespace": namespace},
                suggestion=f"请确认 Pod '{name}' 存在于命名空间 '{namespace}'"
            )


__all__ = [
    "GetPodsTool",
    "GetPodTool",
    "GetPodLogsTool",
    "GetPodEventsTool",
    "DescribePodTool",
]
