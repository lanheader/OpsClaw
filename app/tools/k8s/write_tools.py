"""
K8s 写操作工具（新架构）

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
    group="k8s.write",
    operation_type=OperationType.WRITE,
    risk_level=RiskLevel.HIGH,
    permissions=["k8s.deploy"],
    description="重启 Kubernetes Deployment",
    examples=[
        "restart_deployment(name='nginx-deployment', namespace='default')",
    ],
)
class RestartDeploymentTool(BaseOpTool):
    """
    重启 Deployment 工具

    通过滚动重启的方式重启 Deployment。
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
        """执行工具操作"""
        try:
            logger.info(f"Using K8s SDK to restart deployment {name}")
            result = await self._execute_with_sdk(name, namespace)
            return result
        except Exception as e:
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="rollout restart deployment",
                name=name,
                namespace=namespace
            )
            return result

    async def _execute_with_sdk(self, name: str, namespace: str) -> Dict[str, Any]:
        """使用 SDK 执行"""
        import time

        # 通过添加 annotation 触发滚动重启
        deployment = await self.k8s_client.read_namespaced_deployment(name, namespace)

        # 添加重启 annotation
        if deployment.spec.template.metadata.annotations is None:
            deployment.spec.template.metadata.annotations = {}
        deployment.spec.template.metadata.annotations["kubectl.kubernetes.io/restartedAt"] = str(
            time.time()
        )

        # 更新 deployment
        await self.k8s_client.patch_namespaced_deployment(
            name=name,
            namespace=namespace,
            body=deployment
        )

        return {
            "success": True,
            "data": {
                "name": name,
                "namespace": namespace,
                "message": f"Deployment {name} restarted successfully",
            },
            "execution_mode": "sdk",
            "source": "kubernetes-sdk",
        }


@register_tool(
    group="k8s.write",
    operation_type=OperationType.WRITE,
    risk_level=RiskLevel.HIGH,
    permissions=["k8s.scale"],
    description="扩缩容 Kubernetes Deployment",
    examples=[
        "scale_deployment(name='nginx-deployment', replicas=3, namespace='default')",
    ],
)
class ScaleDeploymentTool(BaseOpTool):
    """
    扩缩容 Deployment 工具

    调整 Deployment 的副本数量。
    """

    def __init__(self):
        from app.integrations.kubernetes.client import K8sClient
        self.k8s_client = K8sClient()
        self.fallback = get_k8s_fallback()

    async def execute(
        self,
        name: str,
        replicas: int,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        try:
            logger.info(f"Using K8s SDK to scale deployment {name} to {replicas} replicas")
            result = await self._execute_with_sdk(name, replicas, namespace)
            return result
        except Exception as e:
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="scale deployment",
                name=name,
                namespace=namespace,
                replicas=replicas
            )
            return result

    async def _execute_with_sdk(self, name: str, replicas: int, namespace: str) -> Dict[str, Any]:
        """使用 SDK 执行"""
        from kubernetes import client

        # 创建 scale 对象
        scale = client.V1Scale(
            spec=client.V1ScaleSpec(replicas=replicas)
        )

        # 执行扩缩容
        await self.k8s_client.patch_namespaced_deployment_scale(
            name=name,
            namespace=namespace,
            body=scale
        )

        return {
            "success": True,
            "data": {
                "name": name,
                "namespace": namespace,
                "replicas": replicas,
                "message": f"Deployment {name} scaled to {replicas} replicas",
            },
            "execution_mode": "sdk",
            "source": "kubernetes-sdk",
        }


@register_tool(
    group="k8s.write",
    operation_type=OperationType.WRITE,
    risk_level=RiskLevel.HIGH,
    permissions=["k8s.deploy_images"],
    description="更新 Deployment 镜像",
    examples=[
        "update_deployment_image(name='nginx-deployment', image='nginx:1.25', namespace='default')",
    ],
)
class UpdateDeploymentImageTool(BaseOpTool):
    """
    更新 Deployment 镜像工具

    更新 Deployment 中容器的镜像版本。
    """

    def __init__(self):
        from app.integrations.kubernetes.client import K8sClient
        self.k8s_client = K8sClient()
        self.fallback = get_k8s_fallback()

    async def execute(
        self,
        name: str,
        image: str,
        container: Optional[str] = None,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        try:
            logger.info(f"Using K8s SDK to update image for deployment {name}")
            result = await self._execute_with_sdk(name, image, container, namespace)
            return result
        except Exception as e:
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="set image deployment",
                name=name,
                namespace=namespace,
                image=image
            )
            return result

    async def _execute_with_sdk(self, name: str, image: str, container: Optional[str], namespace: str) -> Dict[str, Any]:
        """使用 SDK 执行"""
        from kubernetes import client

        # 获取 deployment
        deployment = await self.k8s_client.read_namespaced_deployment(name, namespace)

        # 确定要更新的容器
        if container is None:
            # 默认更新第一个容器
            if deployment.spec.template.spec.containers:
                container = deployment.spec.template.spec.containers[0].name
            else:
                return {
                    "success": False,
                    "error": "Deployment has no containers",
                }

        # 查找并更新容器镜像
        container_found = False
        for c in deployment.spec.template.spec.containers:
            if c.name == container:
                c.image = image
                container_found = True
                break

        if not container_found:
            return {
                "success": False,
                "error": f"Container {container} not found in deployment",
            }

        # 更新 deployment
        await self.k8s_client.patch_namespaced_deployment(
            name=name,
            namespace=namespace,
            body=deployment
        )

        return {
            "success": True,
            "data": {
                "name": name,
                "namespace": namespace,
                "container": container,
                "image": image,
                "message": f"Deployment {name} container {container} image updated to {image}",
            },
            "execution_mode": "sdk",
            "source": "kubernetes-sdk",
        }


__all__ = [
    "RestartDeploymentTool",
    "ScaleDeploymentTool",
    "UpdateDeploymentImageTool",
]
