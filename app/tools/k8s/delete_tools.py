"""
K8s 删除操作工具（新架构）

使用 BaseOpTool 基类和 @register_tool 装饰器。
直接使用 Kubernetes SDK，不使用 CLI 降级。
"""

from typing import Dict, Any, Optional

from kubernetes import client
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


def _log_tool_success(tool_name: str, message: str = None):
    """记录工具执行成功的日志"""
    ctx = get_request_context()
    session_id = ctx.get('session_id', 'no-sess')
    if message:
        logger.info(f"✅ [{session_id}] 工具完成: {tool_name} | {message}")
    else:
        logger.info(f"✅ [{session_id}] 工具完成: {tool_name}")


@register_tool(
    group="k8s.delete",
    operation_type=OperationType.DELETE,
    risk_level=RiskLevel.HIGH,
    permissions=["k8s.delete_pods"],
    description="删除 Kubernetes Pod",
    examples=[
        "delete_pod(name='nginx-pod', namespace='default')",
    ],
)
class DeletePodTool(BaseOpTool):
    """
    删除 Pod 工具

    删除指定的 Pod。
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
        _log_tool_start("delete_pod", name=name, namespace=namespace)
        try:
            self.k8s_client.core_v1.delete_namespaced_pod(
                name=name,
                namespace=namespace
            )

            data = {
                "name": name,
                "namespace": namespace,
                "message": f"Pod {name} 删除命令已发送",
            }

            _log_tool_success("delete_pod", f"Pod {name} 已删除")
            return tool_success_response(data, "delete_pod", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "delete_pod",
                context={"name": name, "namespace": namespace},
                suggestion=f"请先使用 get_pods 工具确认 Pod '{name}' 存在"
            )


@register_tool(
    group="k8s.delete",
    operation_type=OperationType.DELETE,
    risk_level=RiskLevel.HIGH,
    permissions=["k8s.delete_deployments"],
    description="删除 Kubernetes Deployment",
    examples=[
        "delete_deployment(name='nginx-deployment', namespace='default')",
    ],
)
class DeleteDeploymentTool(BaseOpTool):
    """
    删除 Deployment 工具

    删除指定的 Deployment 及其关联的 Pods。
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
        _log_tool_start("delete_deployment", name=name, namespace=namespace)
        try:
            self.k8s_client.apps_v1.delete_namespaced_deployment(
                name=name,
                namespace=namespace
            )

            data = {
                "name": name,
                "namespace": namespace,
                "message": f"Deployment {name} 删除命令已发送，关联的 Pod 将被自动清理",
            }

            _log_tool_success("delete_deployment", f"Deployment {name} 已删除")
            return tool_success_response(data, "delete_deployment", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "delete_deployment",
                context={"name": name, "namespace": namespace},
                suggestion=f"请先使用 get_deployments 工具确认 Deployment '{name}' 存在"
            )


@register_tool(
    group="k8s.delete",
    operation_type=OperationType.DELETE,
    risk_level=RiskLevel.HIGH,
    permissions=["k8s.delete_services"],
    description="删除 Kubernetes Service",
    examples=[
        "delete_service(name='nginx-service', namespace='default')",
    ],
)
class DeleteServiceTool(BaseOpTool):
    """
    删除 Service 工具

    删除指定的 Service。
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
        _log_tool_start("delete_service", name=name, namespace=namespace)
        try:
            self.k8s_client.core_v1.delete_namespaced_service(
                name=name,
                namespace=namespace
            )

            data = {
                "name": name,
                "namespace": namespace,
                "message": f"Service {name} 已删除",
            }

            _log_tool_success("delete_service", f"Service {name} 已删除")
            return tool_success_response(data, "delete_service", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "delete_service",
                context={"name": name, "namespace": namespace},
                suggestion=f"请先使用 get_services 工具确认 Service '{name}' 存在"
            )


@register_tool(
    group="k8s.delete",
    operation_type=OperationType.DELETE,
    risk_level=RiskLevel.HIGH,
    permissions=["k8s.delete_configmaps"],
    description="删除 Kubernetes ConfigMap",
    examples=[
        "delete_configmap(name='app-config', namespace='default')",
    ],
)
class DeleteConfigMapTool(BaseOpTool):
    """
    删除 ConfigMap 工具

    删除指定的 ConfigMap。
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
        _log_tool_start("delete_configmap", name=name, namespace=namespace)
        try:
            self.k8s_client.core_v1.delete_namespaced_config_map(
                name=name,
                namespace=namespace
            )

            data = {
                "name": name,
                "namespace": namespace,
                "message": f"ConfigMap {name} 已删除",
            }

            _log_tool_success("delete_configmap", f"ConfigMap {name} 已删除")
            return tool_success_response(data, "delete_configmap", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "delete_configmap",
                context={"name": name, "namespace": namespace},
                suggestion=f"请确认 ConfigMap '{name}' 存在"
            )


@register_tool(
    group="k8s.delete",
    operation_type=OperationType.DELETE,
    risk_level=RiskLevel.HIGH,
    permissions=["k8s.delete_secrets"],
    description="删除 Kubernetes Secret",
    examples=[
        "delete_secret(name='app-secret', namespace='default')",
    ],
)
class DeleteSecretTool(BaseOpTool):
    """
    删除 Secret 工具

    删除指定的 Secret。
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
        _log_tool_start("delete_secret", name=name, namespace=namespace)
        try:
            self.k8s_client.core_v1.delete_namespaced_secret(
                name=name,
                namespace=namespace
            )

            data = {
                "name": name,
                "namespace": namespace,
                "message": f"Secret {name} 已删除",
            }

            _log_tool_success("delete_secret", f"Secret {name} 已删除")
            return tool_success_response(data, "delete_secret", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "delete_secret",
                context={"name": name, "namespace": namespace},
                suggestion=f"请确认 Secret '{name}' 存在"
            )


@register_tool(
    group="k8s.delete",
    operation_type=OperationType.DELETE,
    risk_level=RiskLevel.HIGH,
    permissions=["k8s.delete_pods"],
    description="强制删除 Kubernetes Pod（删除卡住的 Pod）",
    examples=[
        "force_delete_pod(name='stuck-pod', namespace='default')",
    ],
)
class ForceDeletePodTool(BaseOpTool):
    """
    强制删除 Pod 工具

    强制删除卡住或无法正常删除的 Pod。
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
        _log_tool_start("force_delete_pod", name=name, namespace=namespace)
        try:
            # 使用 grace_period_seconds=0 强制删除
            self.k8s_client.core_v1.delete_namespaced_pod(
                name=name,
                namespace=namespace,
                body=client.V1DeleteOptions(
                    grace_period_seconds=0,
                    propagation_policy="Foreground"
                )
            )

            data = {
                "name": name,
                "namespace": namespace,
                "message": f"Pod {name} 强制删除命令已发送",
            }

            _log_tool_success("force_delete_pod", f"Pod {name} 已强制删除")
            return tool_success_response(data, "force_delete_pod", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "force_delete_pod",
                context={"name": name, "namespace": namespace},
                suggestion=f"请先使用 get_pods 工具确认 Pod '{name}' 存在"
            )


__all__ = [
    "DeletePodTool",
    "DeleteDeploymentTool",
    "DeleteServiceTool",
    "DeleteConfigMapTool",
    "DeleteSecretTool",
    "ForceDeletePodTool",
]
