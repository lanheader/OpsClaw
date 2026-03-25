"""
K8s 写操作工具（新架构）

使用 BaseOpTool 基类和 @register_tool 装饰器。
直接使用 Kubernetes SDK，不使用 CLI 降级。
"""

from typing import Dict, Any, Optional
import time

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

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        name: str,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("restart_deployment", name=name, namespace=namespace)
        try:
            # 先检查 deployment 是否存在
            deployment = self.k8s_client.apps_v1.read_namespaced_deployment(name=name, namespace=namespace)

            # 添加重启 annotation
            if deployment.spec.template.metadata.annotations is None:
                deployment.spec.template.metadata.annotations = {}
            deployment.spec.template.metadata.annotations["kubectl.kubernetes.io/restartedAt"] = str(
                time.time()
            )

            # 更新 deployment
            self.k8s_client.apps_v1.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=deployment
            )

            data = {
                "name": name,
                "namespace": namespace,
                "message": f"Deployment {name} 重启命令已发送，正在执行滚动重启",
            }

            _log_tool_success("restart_deployment", f"Deployment {name} 已触发重启")
            return tool_success_response(data, "restart_deployment", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "restart_deployment",
                context={"name": name, "namespace": namespace},
                suggestion=f"请先使用 get_deployments 工具确认 Deployment '{name}' 存在"
            )


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

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        name: str,
        replicas: int,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("scale_deployment", name=name, replicas=replicas, namespace=namespace)
        try:
            # 创建 scale 对象
            scale = client.V1Scale(
                spec=client.V1ScaleSpec(replicas=replicas)
            )

            # 执行扩缩容
            self.k8s_client.apps_v1.patch_namespaced_deployment_scale(
                name=name,
                namespace=namespace,
                body=scale
            )

            data = {
                "name": name,
                "namespace": namespace,
                "replicas": replicas,
                "message": f"Deployment {name} 副本数已调整为 {replicas}",
            }

            _log_tool_success("scale_deployment", f"副本数调整为 {replicas}")
            return tool_success_response(data, "scale_deployment", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "scale_deployment",
                context={"name": name, "namespace": namespace, "replicas": replicas},
                suggestion=f"请先使用 get_deployments 工具确认 Deployment '{name}' 存在"
            )


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

    def __init__(self, db=None):
        self.k8s_client = _init_k8s_client(db)

    async def execute(
        self,
        name: str,
        image: str,
        container: Optional[str] = None,
        namespace: str = "default",
        **kwargs
    ) -> Dict[str, Any]:
        """执行工具操作"""
        _log_tool_start("update_deployment_image", name=name, image=image, container=container, namespace=namespace)
        try:
            # 获取 deployment
            deployment = self.k8s_client.apps_v1.read_namespaced_deployment(name=name, namespace=namespace)

            # 确定要更新的容器
            if container is None:
                # 默认更新第一个容器
                if deployment.spec.template.spec.containers:
                    container = deployment.spec.template.spec.containers[0].name
                else:
                    return tool_error_response(
                        Exception("Deployment has no containers"),
                        "update_deployment_image",
                        context={"name": name, "namespace": namespace},
                        suggestion=f"Deployment '{name}' 没有配置容器"
                    )

            # 查找并更新容器镜像
            container_found = False
            for c in deployment.spec.template.spec.containers:
                if c.name == container:
                    c.image = image
                    container_found = True
                    break

            if not container_found:
                return tool_error_response(
                    Exception(f"Container {container} not found"),
                    "update_deployment_image",
                    context={"name": name, "namespace": namespace, "container": container},
                    suggestion=f"容器 '{container}' 不存在于 Deployment '{name}' 中，请检查容器名称"
                )

            # 更新 deployment
            self.k8s_client.apps_v1.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=deployment
            )

            data = {
                "name": name,
                "namespace": namespace,
                "container": container,
                "image": image,
                "message": f"Deployment {name} 容器 {container} 镜像已更新为 {image}",
            }

            _log_tool_success("update_deployment_image", f"镜像更新为 {image}")
            return tool_success_response(data, "update_deployment_image", source="kubernetes-sdk")

        except Exception as e:
            return tool_error_response(
                e, "update_deployment_image",
                context={"name": name, "namespace": namespace, "image": image},
                suggestion=f"请先使用 get_deployments 工具确认 Deployment '{name}' 存在"
            )


__all__ = [
    "RestartDeploymentTool",
    "ScaleDeploymentTool",
    "UpdateDeploymentImageTool",
]
