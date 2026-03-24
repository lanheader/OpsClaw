# app/integrations/kubernetes/client.py
"""Kubernetes 客户端 - 只负责连接管理

支持两种认证模式：
1. config 模式：使用 kubeconfig 文件或内容
2. token 模式：使用 ServiceAccount Token
"""

import logging
import os
import tempfile
from typing import Optional, Dict, Any
from urllib3.exceptions import InsecureRequestWarning

try:
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException
    KUBERNETES_AVAILABLE = True
except ImportError:
    KUBERNETES_AVAILABLE = False
    client = None
    config = None
    ApiException = Exception

logger = logging.getLogger(__name__)


class KubernetesClient:
    """
    Kubernetes 客户端

    只负责连接管理和初始化，不定义具体操作方法。
    具体操作由 tools 层使用暴露的 API 客户端执行。

    支持两种认证模式：
    - config: 使用 kubeconfig 文件或内容
    - token: 使用 ServiceAccount Token
    """

    def __init__(
        self,
        auth_mode: str = "config",
        kubeconfig_path: Optional[str] = None,
        kubeconfig_content: Optional[str] = None,
        token: Optional[str] = None,
        api_host: Optional[str] = None,
        ca_cert: Optional[str] = None,
    ):
        """
        初始化 Kubernetes 客户端

        参数：
            auth_mode: 认证模式 ("config" 或 "token")
            kubeconfig_path: kubeconfig 文件路径
            kubeconfig_content: kubeconfig 文件内容
            token: ServiceAccount Token（token 模式）
            api_host: API Server 地址（token 模式）
            ca_cert: CA 证书内容（token 模式）
        """
        if not KUBERNETES_AVAILABLE:
            raise RuntimeError(
                "kubernetes package not installed. "
                "Install with: pip install kubernetes"
            )

        self.auth_mode = auth_mode
        self.kubeconfig_path = kubeconfig_path
        self.kubeconfig_content = kubeconfig_content
        self.token = token
        self.api_host = api_host
        self.ca_cert = ca_cert

        self._core_v1 = None
        self._apps_v1 = None
        self._initialized = False

    def _initialize(self):
        """初始化 Kubernetes 连接"""
        if self._initialized:
            return

        try:
            if self.auth_mode == "token":
                self._init_token_mode()
            else:
                self._init_config_mode()

            self._initialized = True
            logger.info(f"K8s client initialized (mode={self.auth_mode})")

        except Exception as e:
            logger.error(f"Failed to initialize Kubernetes client: {e}")
            raise RuntimeError(f"Kubernetes initialization failed: {e}")

    def _init_config_mode(self):
        """
        使用 kubeconfig 初始化

        优先级：
        1. kubeconfig_content
        2. kubeconfig_path
        3. 环境变量 KUBECONFIG
        4. 默认 kubeconfig 位置
        5. 集内配置
        """
        loaded = False

        # 1. 尝试使用 kubeconfig_content
        if self.kubeconfig_content:
            try:
                with tempfile.NamedTemporaryFile(
                    mode='w',
                    suffix='.yaml',
                    delete=False
                ) as f:
                    f.write(self.kubeconfig_content)
                    temp_path = f.name
                config.load_kube_config(config_file=temp_path)
                os.unlink(temp_path)
                loaded = True
                logger.info("Loaded K8s config from content")
            except Exception as e:
                logger.warning(f"Failed to load kubeconfig content: {e}")

        # 2. 尝试使用 kubeconfig_path
        if not loaded and self.kubeconfig_path:
            try:
                config.load_kube_config(config_file=self.kubeconfig_path)
                loaded = True
                logger.info(f"Loaded K8s config from file: {self.kubeconfig_path}")
            except Exception as e:
                logger.warning(f"Failed to load kubeconfig file: {e}")

        # 3. 尝试使用环境变量 KUBECONFIG
        if not loaded:
            kubeconfig_env = os.getenv("KUBECONFIG")
            if kubeconfig_env and os.path.exists(kubeconfig_env):
                try:
                    config.load_kube_config(config_file=kubeconfig_env)
                    loaded = True
                    logger.info(f"Loaded K8s config from KUBECONFIG: {kubeconfig_env}")
                except Exception as e:
                    logger.warning(f"Failed to load KUBECONFIG: {e}")

        # 4. 尝试默认 kubeconfig 位置
        if not loaded:
            try:
                config.load_kube_config()
                loaded = True
                logger.info("Loaded K8s config from default location")
            except Exception as e:
                logger.debug(f"No default kubeconfig found: {e}")

        # 5. 尝试集内配置
        if not loaded:
            try:
                config.load_incluster_config()
                loaded = True
                logger.info("Loaded in-cluster K8s config")
            except Exception as e:
                logger.debug(f"No in-cluster config found: {e}")

        if not loaded:
            raise RuntimeError(
                "Failed to load Kubernetes config. "
                "Please provide kubeconfig or run inside a Kubernetes cluster."
            )

        # 初始化 API 客户端
        self._core_v1 = client.CoreV1Api()
        self._apps_v1 = client.AppsV1Api()

    def _init_token_mode(self):
        """
        使用 ServiceAccount Token 初始化

        需要：token、api_host（可选 ca_cert）
        """
        if not self.token:
            raise ValueError("Token is required for token auth mode")

        if not self.api_host:
            raise ValueError("API host is required for token auth mode")

        try:
            # 创建配置
            configuration = client.Configuration()

            # 设置 API Host
            configuration.host = self.api_host

            # 设置 Token
            configuration.api_key = {"authorization": f"Bearer {self.token}"}

            # 设置 CA 证书（可选）
            if self.ca_cert:
                # 使用自定义 CA 证书
                with tempfile.NamedTemporaryFile(
                    mode='w',
                    suffix='.crt',
                    delete=False
                ) as f:
                    f.write(self.ca_cert)
                    ca_cert_path = f.name

                configuration.ssl_ca_cert = ca_cert_path
                configuration.verify_ssl = True
                logger.info("Using custom CA certificate")
            else:
                # 不提供 CA 证书时，使用系统默认 CA 信任链
                # 这适用于使用公网信任证书的 API Server
                configuration.verify_ssl = True
                logger.info("Using system default CA certificates (verify_ssl=True)")

            # 创建 API 客户端
            self._core_v1 = client.CoreV1Api(api_client=client.ApiClient(configuration))
            self._apps_v1 = client.AppsV1Api(api_client=client.ApiClient(configuration))

            logger.info(f"Loaded K8s config from token (api_host={self.api_host})")

        except Exception as e:
            raise RuntimeError(f"Failed to initialize token mode: {e}")

    async def check_kubernetes_health(self) -> bool:
        """
        检查 Kubernetes API 是否健康且可访问

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

    @property
    def core_v1(self) -> "client.CoreV1Api":
        """
        获取 CoreV1Api 客户端

        由 tools 层使用，直接调用 SDK 方法。

        示例：
            pods = await client.core_v1.list_namespaced_pod(namespace="default")
        """
        self._initialize()
        return self._core_v1

    @property
    def apps_v1(self) -> "client.AppsV1Api":
        """
        获取 AppsV1Api 客户端

        由 tools 层使用，直接调用 SDK 方法。

        示例：
            deployments = await client.apps_v1.list_namespaced_deployment(namespace="default")
        """
        self._initialize()
        return self._apps_v1

    @property
    def batch_v1(self) -> "client.BatchV1Api":
        """获取 BatchV1Api 客户端"""
        self._initialize()
        return client.BatchV1Api()

    @property
    def networking_v1(self) -> "client.NetworkingV1Api":
        """获取 NetworkingV1Api 客户端"""
        self._initialize()
        return client.NetworkingV1Api()

    @property
    def custom_objects(self) -> "client.CustomObjectsApi":
        """获取 CustomObjectsApi 客户端"""
        self._initialize()
        return client.CustomObjectsApi()


# 单例实例（已弃用 - 推荐使用 create_client 从数据库配置创建）
_kubernetes_client: Optional[KubernetesClient] = None


def create_client(
    db=None,
    auth_mode: Optional[str] = None,
    kubeconfig_path: Optional[str] = None,
    kubeconfig_content: Optional[str] = None,
    token: Optional[str] = None,
    api_host: Optional[str] = None,
    ca_cert: Optional[str] = None,
) -> KubernetesClient:
    """
    创建 Kubernetes 客户端

    参数：
        db: 数据库会话（用于从 SystemSetting 读取配置）
        auth_mode: 认证模式（如果为 None，从数据库读取）
        kubeconfig_path: kubeconfig 文件路径
        kubeconfig_content: kubeconfig 文件内容
        token: ServiceAccount Token
        api_host: API Server 地址
        ca_cert: CA 证书内容

    返回：
        KubernetesClient 实例
    """
    # 如果提供了 db 且没有指定参数，从数据库读取配置
    if db and auth_mode is None:
        from app.core.integration_config import IntegrationConfig

        if not IntegrationConfig.is_k8s_enabled(db):
            raise RuntimeError("K8s integration is not enabled")

        auth_mode = IntegrationConfig.get_k8s_auth_mode(db)

        if auth_mode == "config":
            kubeconfig_content = IntegrationConfig.get_k8s_kubeconfig(db)
        else:  # token
            token = IntegrationConfig.get_k8s_token(db)
            api_host = IntegrationConfig.get_k8s_api_host(db)
            ca_cert = IntegrationConfig.get_k8s_ca_cert(db)

    # 降级：如果没有提供任何配置，尝试使用默认 kubeconfig
    if auth_mode is None:
        auth_mode = "config"

    return KubernetesClient(
        auth_mode=auth_mode,
        kubeconfig_path=kubeconfig_path,
        kubeconfig_content=kubeconfig_content,
        token=token,
        api_host=api_host,
        ca_cert=ca_cert,
    )


def get_kubernetes_client(kubeconfig_path: Optional[str] = None) -> KubernetesClient:
    """
    获取单例 Kubernetes 客户端实例（已弃用）

    注意：此方法仅用于向后兼容，推荐使用 create_client()

    参数：
        kubeconfig_path: 可选的 kubeconfig 路径

    返回：
        KubernetesClient 实例
    """
    global _kubernetes_client

    if _kubernetes_client is None:
        if kubeconfig_path is None:
            kubeconfig_path = os.getenv("KUBECONFIG")

        _kubernetes_client = KubernetesClient(
            auth_mode="config",
            kubeconfig_path=kubeconfig_path
        )

    return _kubernetes_client
