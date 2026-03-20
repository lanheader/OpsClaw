# app/tools/k8s_sdk_tools.py
"""Kubernetes SDK 工具 - 使用 kubernetes Python 客户端"""

from typing import Dict, Any, Optional, List
from langchain_core.tools import tool
import logging

logger = logging.getLogger(__name__)


@tool
async def get_pods_sdk(
    namespace: str = "default", pod_name: Optional[str] = None, label_selector: Optional[str] = None
) -> Dict[str, Any]:
    """
    使用 Kubernetes SDK 获取 Pod 信息。

    如果 SDK 不可用或未配置，返回降级建议。

    参数：
        namespace: 命名空间
        pod_name: 可选的 Pod 名称（如果指定，只获取该 Pod）
        label_selector: 可选的标签选择器（如 "app=nginx"）

    返回：
        包含以下内容的字典：
        - success: bool（是否成功）
        - execution_mode: str（"sdk" 或 "cli"）
        - needs_fallback: bool（是否需要降级）
        - fallback_suggestion: Optional[str]（降级命令建议）
        - data: Optional[Dict]（Pod 数据）
        - error: Optional[str]（错误信息）

    示例：
        # 获取所有 Pod
        result = await get_pods_sdk.ainvoke({"namespace": "default"})

        # 获取特定 Pod
        result = await get_pods_sdk.ainvoke({
            "namespace": "default",
            "pod_name": "my-pod"
        })

        # 使用标签选择器
        result = await get_pods_sdk.ainvoke({
            "namespace": "default",
            "label_selector": "app=nginx"
        })
    """
    try:
        from kubernetes import client, config
        from kubernetes.client.rest import ApiException

        # 尝试加载 kubeconfig
        try:
            config.load_kube_config()
        except Exception as e:
            # kubeconfig 不可用，返回降级建议
            logger.warning(f"无法加载 kubeconfig: {e}")

            # 生成降级命令
            fallback_cmd = f"kubectl get pods -n {namespace}"
            if pod_name:
                fallback_cmd = f"kubectl get pod {pod_name} -n {namespace} -o json"
            elif label_selector:
                fallback_cmd = f"kubectl get pods -n {namespace} -l {label_selector} -o json"
            else:
                fallback_cmd = f"kubectl get pods -n {namespace} -o json"

            return {
                "success": False,
                "execution_mode": "sdk",
                "needs_fallback": True,
                "fallback_suggestion": fallback_cmd,
                "error": f"Kubernetes SDK 不可用: {str(e)}",
            }

        # 创建 API 客户端
        v1 = client.CoreV1Api()

        # 获取 Pod 信息
        if pod_name:
            # 获取单个 Pod
            pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            pods = [pod]
        else:
            # 获取多个 Pod
            if label_selector:
                pod_list = v1.list_namespaced_pod(
                    namespace=namespace, label_selector=label_selector
                )
            else:
                pod_list = v1.list_namespaced_pod(namespace=namespace)
            pods = pod_list.items

        # 转换为字典格式
        pods_data = []
        for pod in pods:
            # 计算重启次数
            restart_count = 0
            if pod.status.container_statuses:
                restart_count = sum(cs.restart_count for cs in pod.status.container_statuses)

            # 提取关键信息
            pod_info = {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "status": pod.status.phase,
                "restarts": restart_count,
                "node": pod.spec.node_name,
                "ip": pod.status.pod_ip,
                "created_at": (
                    pod.metadata.creation_timestamp.isoformat()
                    if pod.metadata.creation_timestamp
                    else None
                ),
                "labels": pod.metadata.labels or {},
                "conditions": [],
            }

            # 添加条件信息
            if pod.status.conditions:
                for condition in pod.status.conditions:
                    pod_info["conditions"].append(
                        {
                            "type": condition.type,
                            "status": condition.status,
                            "reason": condition.reason,
                            "message": condition.message,
                        }
                    )

            # 添加容器信息
            containers = []
            if pod.spec.containers:
                for container in pod.spec.containers:
                    containers.append(
                        {"name": container.name, "image": container.image, "ready": False}  # 默认值
                    )

            # 更新容器就绪状态
            if pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    for c in containers:
                        if c["name"] == cs.name:
                            c["ready"] = cs.ready
                            c["state"] = (
                                "running"
                                if cs.state.running
                                else ("waiting" if cs.state.waiting else "terminated")
                            )

            pod_info["containers"] = containers
            pods_data.append(pod_info)

        logger.info(f"✅ SDK 成功获取 {len(pods_data)} 个 Pod")

        return {
            "success": True,
            "execution_mode": "sdk",
            "needs_fallback": False,
            "data": {"pods": pods_data, "count": len(pods_data)},
        }

    except Exception as e:
        # SDK 执行失败，返回降级建议
        logger.error(f"SDK 执行失败: {e}", exc_info=True)

        # 生成降级命令
        fallback_cmd = f"kubectl get pods -n {namespace}"
        if pod_name:
            fallback_cmd = f"kubectl get pod {pod_name} -n {namespace} -o json"
        elif label_selector:
            fallback_cmd = f"kubectl get pods -n {namespace} -l {label_selector} -o json"
        else:
            fallback_cmd = f"kubectl get pods -n {namespace} -o json"

        return {
            "success": False,
            "execution_mode": "sdk",
            "needs_fallback": True,
            "fallback_suggestion": fallback_cmd,
            "error": f"SDK 执行失败: {str(e)}",
        }


@tool
async def get_services_sdk(
    namespace: str = "default", service_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    使用 Kubernetes SDK 获取 Service 信息。

    参数：
        namespace: 命名空间
        service_name: 可选的 Service 名称

    返回：
        包含以下内容的字典：
        - success: bool
        - execution_mode: str
        - needs_fallback: bool
        - fallback_suggestion: Optional[str]
        - data: Optional[Dict]
        - error: Optional[str]
    """
    try:
        from kubernetes import client, config
        from kubernetes.client.rest import ApiException

        # 尝试加载 kubeconfig
        try:
            config.load_kube_config()
        except Exception as e:
            fallback_cmd = f"kubectl get services -n {namespace} -o json"
            if service_name:
                fallback_cmd = f"kubectl get service {service_name} -n {namespace} -o json"

            return {
                "success": False,
                "execution_mode": "sdk",
                "needs_fallback": True,
                "fallback_suggestion": fallback_cmd,
                "error": f"Kubernetes SDK 不可用: {str(e)}",
            }

        # 创建 API 客户端
        v1 = client.CoreV1Api()

        # 获取 Service 信息
        if service_name:
            service = v1.read_namespaced_service(name=service_name, namespace=namespace)
            services = [service]
        else:
            service_list = v1.list_namespaced_service(namespace=namespace)
            services = service_list.items

        # 转换为字典格式
        services_data = []
        for svc in services:
            svc_info = {
                "name": svc.metadata.name,
                "namespace": svc.metadata.namespace,
                "type": svc.spec.type,
                "cluster_ip": svc.spec.cluster_ip,
                "external_ips": svc.spec.external_i_ps or [],
                "ports": [],
                "selector": svc.spec.selector or {},
                "created_at": (
                    svc.metadata.creation_timestamp.isoformat()
                    if svc.metadata.creation_timestamp
                    else None
                ),
            }

            # 添加端口信息
            if svc.spec.ports:
                for port in svc.spec.ports:
                    svc_info["ports"].append(
                        {
                            "name": port.name,
                            "port": port.port,
                            "target_port": str(port.target_port) if port.target_port else None,
                            "protocol": port.protocol,
                            "node_port": port.node_port,
                        }
                    )

            services_data.append(svc_info)

        logger.info(f"✅ SDK 成功获取 {len(services_data)} 个 Service")

        return {
            "success": True,
            "execution_mode": "sdk",
            "needs_fallback": False,
            "data": {"services": services_data, "count": len(services_data)},
        }

    except Exception as e:
        logger.error(f"SDK 执行失败: {e}", exc_info=True)

        fallback_cmd = f"kubectl get services -n {namespace} -o json"
        if service_name:
            fallback_cmd = f"kubectl get service {service_name} -n {namespace} -o json"

        return {
            "success": False,
            "execution_mode": "sdk",
            "needs_fallback": True,
            "fallback_suggestion": fallback_cmd,
            "error": f"SDK 执行失败: {str(e)}",
        }


@tool
async def get_nodes_sdk() -> Dict[str, Any]:
    """
    使用 Kubernetes SDK 获取 Node 信息。

    返回：
        包含以下内容的字典：
        - success: bool
        - execution_mode: str
        - needs_fallback: bool
        - fallback_suggestion: Optional[str]
        - data: Optional[Dict]
        - error: Optional[str]
    """
    try:
        from kubernetes import client, config
        from kubernetes.client.rest import ApiException

        # 尝试加载 kubeconfig
        try:
            config.load_kube_config()
        except Exception as e:
            return {
                "success": False,
                "execution_mode": "sdk",
                "needs_fallback": True,
                "fallback_suggestion": "kubectl get nodes -o json",
                "error": f"Kubernetes SDK 不可用: {str(e)}",
            }

        # 创建 API 客户端
        v1 = client.CoreV1Api()

        # 获取 Node 信息
        node_list = v1.list_node()
        nodes = node_list.items

        # 转换为字典格式
        nodes_data = []
        for node in nodes:
            # 提取资源信息
            capacity = node.status.capacity or {}
            allocatable = node.status.allocatable or {}

            node_info = {
                "name": node.metadata.name,
                "status": "Unknown",
                "roles": [],
                "age": (
                    node.metadata.creation_timestamp.isoformat()
                    if node.metadata.creation_timestamp
                    else None
                ),
                "version": node.status.node_info.kubelet_version if node.status.node_info else None,
                "capacity": {
                    "cpu": capacity.get("cpu"),
                    "memory": capacity.get("memory"),
                    "pods": capacity.get("pods"),
                },
                "allocatable": {
                    "cpu": allocatable.get("cpu"),
                    "memory": allocatable.get("memory"),
                    "pods": allocatable.get("pods"),
                },
                "conditions": [],
            }

            # 提取角色
            if node.metadata.labels:
                for key in node.metadata.labels:
                    if "node-role.kubernetes.io/" in key:
                        role = key.split("/")[1]
                        node_info["roles"].append(role)

            # 提取状态
            if node.status.conditions:
                for condition in node.status.conditions:
                    if condition.type == "Ready":
                        node_info["status"] = "Ready" if condition.status == "True" else "NotReady"

                    node_info["conditions"].append(
                        {
                            "type": condition.type,
                            "status": condition.status,
                            "reason": condition.reason,
                            "message": condition.message,
                        }
                    )

            nodes_data.append(node_info)

        logger.info(f"✅ SDK 成功获取 {len(nodes_data)} 个 Node")

        return {
            "success": True,
            "execution_mode": "sdk",
            "needs_fallback": False,
            "data": {"nodes": nodes_data, "count": len(nodes_data)},
        }

    except Exception as e:
        logger.error(f"SDK 执行失败: {e}", exc_info=True)

        return {
            "success": False,
            "execution_mode": "sdk",
            "needs_fallback": True,
            "fallback_suggestion": "kubectl get nodes -o json",
            "error": f"SDK 执行失败: {str(e)}",
        }
