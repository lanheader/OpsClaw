# app/integrations/kubernetes/client.py
"""用于 Pod 和 Deployment 操作的 Kubernetes 客户端"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, UTC
import os

try:
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException

    KUBERNETES_AVAILABLE = True
except ImportError:
    KUBERNETES_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("kubernetes package not installed. K8s integration will be unavailable.")

logger = logging.getLogger(__name__)


class KubernetesClient:
    """
    用于 Kubernetes 操作的客户端。

    支持：
    - Pod 日志检索
    - Deployment 重启
    - Pod 状态检查
    - Deployment 扩缩容
    - 自动检测集群内/集群外模式
    """

    def __init__(self, kubeconfig_path: Optional[str] = None):
        """
        初始化 Kubernetes 客户端。

        参数：
            kubeconfig_path: kubeconfig 文件的可选路径

        异常：
            RuntimeError: 如果 kubernetes 包不可用
        """
        if not KUBERNETES_AVAILABLE:
            raise RuntimeError(
                "kubernetes package not installed. " "Install with: pip install kubernetes"
            )

        self.kubeconfig_path = kubeconfig_path
        self._core_v1 = None
        self._apps_v1 = None
        self._in_cluster = False
        self._initialized = False

    def _initialize(self):
        """
        初始化 Kubernetes 配置。

        首先尝试集群内配置，然后回退到 kubeconfig。
        """
        if self._initialized:
            return

        try:
            # 首先尝试集群内配置
            config.load_incluster_config()
            self._in_cluster = True
            logger.info("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            # 回退到 kubeconfig
            try:
                if self.kubeconfig_path:
                    config.load_kube_config(config_file=self.kubeconfig_path)
                else:
                    config.load_kube_config()
                self._in_cluster = False
                logger.info("Loaded kubeconfig from file")
            except Exception as e:
                logger.error(f"Failed to load Kubernetes config: {e}")
                raise RuntimeError(f"Kubernetes configuration failed: {e}")

        # 初始化 API 客户端
        self._core_v1 = client.CoreV1Api()
        self._apps_v1 = client.AppsV1Api()
        self._initialized = True

    async def get_pod_logs(
        self,
        pod_name: str,
        namespace: str = "default",
        container: Optional[str] = None,
        tail_lines: int = 100,
        since_seconds: Optional[int] = None,
    ) -> List[str]:
        """
        获取 Kubernetes pod 的日志。

        参数：
            pod_name: Pod 名称
            namespace: Kubernetes 命名空间
            container: 可选的容器名称（如果 pod 有多个容器）
            tail_lines: 要检索的最近日志行数
            since_seconds: 仅返回比此秒数更新的日志

        返回：
            日志行列表

        示例：
            logs = await client.get_pod_logs(
                pod_name="redis-prod-0",
                namespace="production",
                tail_lines=200
            )
        """
        self._initialize()

        try:
            log_str = self._core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                container=container,
                tail_lines=tail_lines,
                since_seconds=since_seconds,
            )

            return log_str.strip().split("\n") if log_str else []

        except ApiException as e:
            logger.error(f"K8s API error getting pod logs: {e}")
            return []
        except Exception as e:
            logger.exception(f"Error getting pod logs: {e}")
            return []

    async def get_deployment_pods(
        self, deployment_name: str, namespace: str = "default"
    ) -> List[Dict[str, Any]]:
        """
        获取 deployment 的所有 pod。

        参数：
            deployment_name: Deployment 名称
            namespace: Kubernetes 命名空间

        返回：
            pod 信息字典列表

        示例：
            pods = await client.get_deployment_pods(
                deployment_name="user-service",
                namespace="production"
            )
        """
        self._initialize()

        try:
            # 获取 deployment 以查找 selector
            deployment = self._apps_v1.read_namespaced_deployment(
                name=deployment_name, namespace=namespace
            )

            selector_labels = deployment.spec.selector.match_labels
            label_selector = ",".join(f"{k}={v}" for k, v in selector_labels.items())

            # 获取匹配 selector 的 pod
            pods = self._core_v1.list_namespaced_pod(
                namespace=namespace, label_selector=label_selector
            )

            pod_info = []
            for pod in pods.items:
                pod_info.append(
                    {
                        "name": pod.metadata.name,
                        "phase": pod.status.phase,
                        "ready": self._is_pod_ready(pod),
                        "restarts": sum(
                            cs.restart_count for cs in pod.status.container_statuses or []
                        ),
                        "created": pod.metadata.creation_timestamp,
                    }
                )

            return pod_info

        except ApiException as e:
            logger.error(f"K8s API error getting deployment pods: {e}")
            return []
        except Exception as e:
            logger.exception(f"Error getting deployment pods: {e}")
            return []

    async def restart_deployment(self, deployment_name: str, namespace: str = "default") -> bool:
        """
        通过更新 restart annotation 重启 deployment。

        参数：
            deployment_name: Deployment 名称
            namespace: Kubernetes 命名空间

        返回：
            如果成功则返回 True，否则返回 False

        示例：
            success = await client.restart_deployment(
                deployment_name="user-service",
                namespace="production"
            )
        """
        self._initialize()

        try:
            # 获取当前 deployment
            deployment = self._apps_v1.read_namespaced_deployment(
                name=deployment_name, namespace=namespace
            )

            # 更新 restart annotation
            if deployment.spec.template.metadata.annotations is None:
                deployment.spec.template.metadata.annotations = {}

            deployment.spec.template.metadata.annotations["kubectl.kubernetes.io/restartedAt"] = (
                datetime.now(UTC).isoformat()
            )

            # Patch deployment
            self._apps_v1.patch_namespaced_deployment(
                name=deployment_name, namespace=namespace, body=deployment
            )

            logger.info(f"Restarted deployment {deployment_name} in namespace {namespace}")
            return True

        except ApiException as e:
            logger.error(f"K8s API error restarting deployment: {e}")
            return False
        except Exception as e:
            logger.exception(f"Error restarting deployment: {e}")
            return False

    async def scale_deployment(
        self, deployment_name: str, replicas: int, namespace: str = "default"
    ) -> bool:
        """
        将 deployment 扩缩容到指定副本数。

        参数：
            deployment_name: Deployment 名称
            replicas: 目标副本数
            namespace: Kubernetes 命名空间

        返回：
            如果成功则返回 True，否则返回 False

        示例：
            success = await client.scale_deployment(
                deployment_name="user-service",
                replicas=5,
                namespace="production"
            )
        """
        self._initialize()

        try:
            # 扩缩容 deployment
            self._apps_v1.patch_namespaced_deployment_scale(
                name=deployment_name, namespace=namespace, body={"spec": {"replicas": replicas}}
            )

            logger.info(f"Scaled deployment {deployment_name} to {replicas} replicas")
            return True

        except ApiException as e:
            logger.error(f"K8s API error scaling deployment: {e}")
            return False
        except Exception as e:
            logger.exception(f"Error scaling deployment: {e}")
            return False

    async def get_pod_status(self, pod_name: str, namespace: str = "default") -> Dict[str, Any]:
        """
        获取 pod 的详细状态。

        参数：
            pod_name: Pod 名称
            namespace: Kubernetes 命名空间

        返回：
            包含 pod 状态信息的字典

        示例：
            status = await client.get_pod_status(
                pod_name="redis-prod-0",
                namespace="production"
            )
        """
        self._initialize()

        try:
            pod = self._core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)

            return {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "phase": pod.status.phase,
                "ready": self._is_pod_ready(pod),
                "restarts": sum(cs.restart_count for cs in pod.status.container_statuses or []),
                "conditions": [
                    {"type": c.type, "status": c.status} for c in pod.status.conditions or []
                ],
                "created": pod.metadata.creation_timestamp,
                "node": pod.spec.node_name,
            }

        except ApiException as e:
            logger.error(f"K8s API error getting pod status: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.exception(f"Error getting pod status: {e}")
            return {"error": str(e)}

    async def check_kubernetes_health(self) -> bool:
        """
        检查 Kubernetes API 是否健康且可访问。

        返回：
            如果 K8s API 可访问则返回 True，否则返回 False
        """
        try:
            self._initialize()
            # 尝试列出命名空间作为健康检查
            self._core_v1.list_namespace(limit=1)
            return True
        except Exception as e:
            logger.error(f"Kubernetes health check failed: {e}")
            return False

    def is_in_cluster(self) -> bool:
        """
        检查是否在集群内运行或使用 kubeconfig。

        返回：
            如果在集群内则返回 True，使用 kubeconfig 则返回 False
        """
        self._initialize()
        return self._in_cluster

    def _is_pod_ready(self, pod) -> bool:
        """检查 pod 是否就绪"""
        if not pod.status.conditions:
            return False

        for condition in pod.status.conditions:
            if condition.type == "Ready":
                return condition.status == "True"

        return False


# 单例实例
_kubernetes_client: Optional[KubernetesClient] = None


def get_kubernetes_client(kubeconfig_path: Optional[str] = None) -> KubernetesClient:
    """
    获取单例 Kubernetes 客户端实例。

    参数：
        kubeconfig_path: 可选的 kubeconfig 路径（仅在首次调用时使用）

    返回：
        KubernetesClient 实例

    异常：
        RuntimeError: 如果 kubernetes 包不可用
    """
    global _kubernetes_client

    if _kubernetes_client is None:
        if kubeconfig_path is None:
            kubeconfig_path = os.getenv("KUBECONFIG")

        _kubernetes_client = KubernetesClient(kubeconfig_path=kubeconfig_path)

    return _kubernetes_client
