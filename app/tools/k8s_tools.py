"""K8s工具集"""

from typing import Dict, Any, List


def get_pod_status(namespace: str = "default", pod_name: str = None) -> Dict[str, Any]:
    """
    获取Pod状态

    Args:
        namespace: 命名空间
        pod_name: Pod名称，如果为None则获取所有Pod

    Returns:
        Pod状态信息
    """
    # 模拟实现，实际应该调用kubernetes客户端
    return {
        "pods": [
            {
                "name": "app-pod-1",
                "namespace": namespace,
                "status": "Running",
                "restarts": 0,
                "age": "2d",
            },
            {
                "name": "app-pod-2",
                "namespace": namespace,
                "status": "Running",
                "restarts": 2,
                "age": "2d",
            },
        ]
    }


def get_service_info(namespace: str = "default") -> Dict[str, Any]:
    """获取Service信息"""
    return {
        "services": [
            {
                "name": "app-service",
                "namespace": namespace,
                "type": "ClusterIP",
                "cluster_ip": "10.0.0.1",
                "ports": [{"port": 80, "target_port": 8080}],
            }
        ]
    }


def get_deployment_info(namespace: str = "default") -> Dict[str, Any]:
    """获取Deployment信息"""
    return {
        "deployments": [
            {
                "name": "app-deployment",
                "namespace": namespace,
                "replicas": 3,
                "ready_replicas": 3,
                "available_replicas": 3,
            }
        ]
    }


def get_node_info() -> Dict[str, Any]:
    """获取Node信息"""
    return {
        "nodes": [
            {
                "name": "node-1",
                "status": "Ready",
                "cpu_capacity": "4",
                "memory_capacity": "8Gi",
                "cpu_usage": "50%",
                "memory_usage": "60%",
            }
        ]
    }


def scale_deployment(namespace: str, deployment: str, replicas: int) -> Dict[str, Any]:
    """扩缩容Deployment"""
    return {
        "success": True,
        "message": f"Scaled {deployment} to {replicas} replicas",
        "namespace": namespace,
        "deployment": deployment,
        "replicas": replicas,
    }


def restart_deployment(namespace: str, deployment: str) -> Dict[str, Any]:
    """重启Deployment"""
    return {
        "success": True,
        "message": f"Restarted deployment {deployment}",
        "namespace": namespace,
        "deployment": deployment,
    }


def delete_pod(namespace: str, pod_name: str) -> Dict[str, Any]:
    """删除Pod"""
    return {
        "success": True,
        "message": f"Deleted pod {pod_name}",
        "namespace": namespace,
        "pod": pod_name,
    }


def count_pods(namespace: str = "all") -> Dict[str, Any]:
    """
    统计Pod数量

    Args:
        namespace: 命名空间，"all"表示所有命名空间

    Returns:
        Pod数量统计信息
    """
    if namespace == "all":
        return {
            "total": 45,
            "by_namespace": {
                "default": 12,
                "kube-system": 15,
                "monitoring": 8,
                "production": 10,
            },
            "by_status": {
                "Running": 40,
                "Pending": 2,
                "Failed": 1,
                "Succeeded": 2,
            },
        }
    else:
        return {
            "namespace": namespace,
            "total": 12,
            "by_status": {
                "Running": 10,
                "Pending": 1,
                "Failed": 1,
            },
        }


def count_deployments(namespace: str = "all") -> Dict[str, Any]:
    """
    统计Deployment数量

    Args:
        namespace: 命名空间，"all"表示所有命名空间

    Returns:
        Deployment数量统计信息
    """
    if namespace == "all":
        return {
            "total": 18,
            "by_namespace": {
                "default": 5,
                "production": 8,
                "staging": 3,
                "monitoring": 2,
            },
            "healthy": 16,
            "unhealthy": 2,
        }
    else:
        return {
            "namespace": namespace,
            "total": 5,
            "healthy": 4,
            "unhealthy": 1,
        }


def get_top_resource_pods(sort_by: str = "memory", limit: int = 20) -> Dict[str, Any]:
    """
    获取资源消耗最高的Pod

    Args:
        sort_by: 排序依据，可选 "memory" 或 "cpu"
        limit: 返回的Pod数量限制

    Returns:
        资源使用最高的Pod列表
    """
    if sort_by == "memory":
        return {
            "sort_by": "memory",
            "limit": limit,
            "pods": [
                {
                    "namespace": "production",
                    "name": "app-backend-7d8f9c5b6-x9k2m",
                    "cpu": "450m",
                    "memory": "2.5Gi",
                    "memory_percent": 85.3,
                },
                {
                    "namespace": "production",
                    "name": "database-primary-0",
                    "cpu": "800m",
                    "memory": "2.2Gi",
                    "memory_percent": 78.9,
                },
                {
                    "namespace": "monitoring",
                    "name": "prometheus-server-0",
                    "cpu": "350m",
                    "memory": "1.8Gi",
                    "memory_percent": 72.1,
                },
            ],
        }
    else:  # cpu
        return {
            "sort_by": "cpu",
            "limit": limit,
            "pods": [
                {
                    "namespace": "production",
                    "name": "database-primary-0",
                    "cpu": "800m",
                    "memory": "2.2Gi",
                    "cpu_percent": 80.0,
                },
                {
                    "namespace": "production",
                    "name": "app-backend-7d8f9c5b6-x9k2m",
                    "cpu": "450m",
                    "memory": "2.5Gi",
                    "cpu_percent": 45.0,
                },
                {
                    "namespace": "monitoring",
                    "name": "prometheus-server-0",
                    "cpu": "350m",
                    "memory": "1.8Gi",
                    "cpu_percent": 35.0,
                },
            ],
        }


def get_pod_logs(namespace: str, pod_name: str, tail: int = 100) -> Dict[str, Any]:
    """
    获取Pod日志

    Args:
        namespace: 命名空间
        pod_name: Pod名称
        tail: 返回最后N行日志

    Returns:
        Pod日志信息
    """
    return {
        "namespace": namespace,
        "pod": pod_name,
        "tail": tail,
        "logs": [
            "2026-03-15 10:23:45 INFO Starting application...",
            "2026-03-15 10:23:46 INFO Connected to database",
            "2026-03-15 10:23:47 INFO Server listening on port 8080",
            "2026-03-15 10:24:12 WARN High memory usage detected: 85%",
            "2026-03-15 10:24:15 ERROR Failed to connect to cache: connection timeout",
            "2026-03-15 10:24:16 INFO Retrying cache connection...",
            "2026-03-15 10:24:17 INFO Cache connection established",
        ],
        "total_lines": 7,
    }


def get_node_resource_usage(node_name: str = None) -> Dict[str, Any]:
    """
    获取节点资源使用情况

    Args:
        node_name: 节点名称，如果为None则获取所有节点

    Returns:
        节点资源使用信息
    """
    if node_name:
        return {
            "node": node_name,
            "status": "Ready",
            "cpu": {
                "capacity": "8",
                "allocatable": "7.8",
                "usage": "4.5",
                "usage_percent": 57.7,
            },
            "memory": {
                "capacity": "16Gi",
                "allocatable": "15.2Gi",
                "usage": "10.8Gi",
                "usage_percent": 71.1,
            },
            "disk": {
                "capacity": "100Gi",
                "usage": "65Gi",
                "usage_percent": 65.0,
            },
            "pods": {
                "capacity": 110,
                "usage": 45,
            },
        }
    else:
        return {
            "nodes": [
                {
                    "name": "node-1",
                    "status": "Ready",
                    "cpu_usage_percent": 57.7,
                    "memory_usage_percent": 71.1,
                    "disk_usage_percent": 65.0,
                    "pods": 45,
                },
                {
                    "name": "node-2",
                    "status": "Ready",
                    "cpu_usage_percent": 42.3,
                    "memory_usage_percent": 58.9,
                    "disk_usage_percent": 52.0,
                    "pods": 38,
                },
                {
                    "name": "node-3",
                    "status": "Ready",
                    "cpu_usage_percent": 68.5,
                    "memory_usage_percent": 82.3,
                    "disk_usage_percent": 78.0,
                    "pods": 52,
                },
            ],
            "summary": {
                "total_nodes": 3,
                "ready_nodes": 3,
                "avg_cpu_usage": 56.2,
                "avg_memory_usage": 70.8,
                "avg_disk_usage": 65.0,
                "total_pods": 135,
            },
        }
