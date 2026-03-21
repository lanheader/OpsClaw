"""
K8s 删除操作工具（新架构）

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
        """
        执行工具操作

        Args:
            name: Pod 名称
            namespace: 命名空间

        Returns:
            执行结果字典
        """
        try:
            logger.info(f"Using K8s SDK to delete pod {name}")
            result = await self._execute_with_sdk(name, namespace)
            return result
        except Exception as e:
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="delete pod",
                name=name,
                namespace=namespace
            )
            return result

    async def _execute_with_sdk(self, name: str, namespace: str) -> Dict[str, Any]:
        """使用 SDK 执行"""
        await self.k8s_client.delete_namespaced_pod(
            name=name,
            namespace=namespace
        )

        return {
            "success": True,
            "data": {
                "name": name,
                "namespace": namespace,
                "message": f"Pod {name} deleted successfully",
            },
            "execution_mode": "sdk",
            "source": "kubernetes-sdk",
        }


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
        """
        执行工具操作

        Args:
            name: Deployment 名称
            namespace: 命名空间

        Returns:
            执行结果字典
        """
        try:
            logger.info(f"Using K8s SDK to delete deployment {name}")
            result = await self._execute_with_sdk(name, namespace)
            return result
        except Exception as e:
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="delete deployment",
                name=name,
                namespace=namespace
            )
            return result

    async def _execute_with_sdk(self, name: str, namespace: str) -> Dict[str, Any]:
        """使用 SDK 执行"""
        await self.k8s_client.delete_namespaced_deployment(
            name=name,
            namespace=namespace
        )

        return {
            "success": True,
            "data": {
                "name": name,
                "namespace": namespace,
                "message": f"Deployment {name} deleted successfully",
            },
            "execution_mode": "sdk",
            "source": "kubernetes-sdk",
        }


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
        """
        执行工具操作

        Args:
            name: Service 名称
            namespace: 命名空间

        Returns:
            执行结果字典
        """
        try:
            logger.info(f"Using K8s SDK to delete service {name}")
            result = await self._execute_with_sdk(name, namespace)
            return result
        except Exception as e:
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="delete service",
                name=name,
                namespace=namespace
            )
            return result

    async def _execute_with_sdk(self, name: str, namespace: str) -> Dict[str, Any]:
        """使用 SDK 执行"""
        await self.k8s_client.delete_namespaced_service(
            name=name,
            namespace=namespace
        )

        return {
            "success": True,
            "data": {
                "name": name,
                "namespace": namespace,
                "message": f"Service {name} deleted successfully",
            },
            "execution_mode": "sdk",
            "source": "kubernetes-sdk",
        }


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
        """
        执行工具操作

        Args:
            name: ConfigMap 名称
            namespace: 命名空间

        Returns:
            执行结果字典
        """
        try:
            logger.info(f"Using K8s SDK to delete configmap {name}")
            result = await self._execute_with_sdk(name, namespace)
            return result
        except Exception as e:
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="delete configmap",
                name=name,
                namespace=namespace
            )
            return result

    async def _execute_with_sdk(self, name: str, namespace: str) -> Dict[str, Any]:
        """使用 SDK 执行"""
        await self.k8s_client.delete_namespaced_config_map(
            name=name,
            namespace=namespace
        )

        return {
            "success": True,
            "data": {
                "name": name,
                "namespace": namespace,
                "message": f"ConfigMap {name} deleted successfully",
            },
            "execution_mode": "sdk",
            "source": "kubernetes-sdk",
        }


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
        """
        执行工具操作

        Args:
            name: Secret 名称
            namespace: 命名空间

        Returns:
            执行结果字典
        """
        try:
            logger.info(f"Using K8s SDK to delete secret {name}")
            result = await self._execute_with_sdk(name, namespace)
            return result
        except Exception as e:
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="delete secret",
                name=name,
                namespace=namespace
            )
            return result

    async def _execute_with_sdk(self, name: str, namespace: str) -> Dict[str, Any]:
        """使用 SDK 执行"""
        await self.k8s_client.delete_namespaced_secret(
            name=name,
            namespace=namespace
        )

        return {
            "success": True,
            "data": {
                "name": name,
                "namespace": namespace,
                "message": f"Secret {name} deleted successfully",
            },
            "execution_mode": "sdk",
            "source": "kubernetes-sdk",
        }


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
        """
        执行工具操作

        Args:
            name: Pod 名称
            namespace: 命名空间

        Returns:
            执行结果字典
        """
        try:
            logger.info(f"Using K8s SDK to force delete pod {name}")
            result = await self._execute_with_sdk(name, namespace)
            return result
        except Exception as e:
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="delete pod --force --grace-period 0",
                name=name,
                namespace=namespace
            )
            return result

    async def _execute_with_sdk(self, name: str, namespace: str) -> Dict[str, Any]:
        """使用 SDK 执行"""
        from kubernetes import client

        # 使用 grace_period_seconds=0 强制删除
        await self.k8s_client.delete_namespaced_pod(
            name=name,
            namespace=namespace,
            body=client.V1DeleteOptions(
                grace_period_seconds=0,
                propagation_policy="Foreground"
            )
        )

        return {
            "success": True,
            "data": {
                "name": name,
                "namespace": namespace,
                "message": f"Pod {name} force deleted successfully",
            },
            "execution_mode": "sdk",
            "source": "kubernetes-sdk",
        }


__all__ = [
    "DeletePodTool",
    "DeleteDeploymentTool",
    "DeleteServiceTool",
    "DeleteConfigMapTool",
    "DeleteSecretTool",
    "ForceDeletePodTool",
]
