"""
Data Agent - 数据采集子智能体

增强版：使用 ReWOO 模式实现并行数据采集

功能：
1. 规划采集步骤（Planner）
2. 并行执行采集（Worker）
3. 整合结果（Solver）

ReWOO 模式优势：
- 执行效率高（并行采集）
- 减少 Token 消耗（无需中间观察）
- 步骤可并行

⭐ system_prompt 将动态从数据库加载
"""

from app.tools import get_tools_by_package
from app.services.enhanced_data_agent_service import get_enhanced_data_agent_service

# 基础配置
DATA_AGENT_CONFIG = {
    "name": "data-agent",
    "description": "执行数据采集命令,调用 K8s/Prometheus/Loki 工具获取集群数据（支持 ReWOO 并行采集）",
    "system_prompt": None,  # 将动态从数据库加载
    "tools": [
        # K8s 读操作
        *get_tools_by_package("k8s"),
        # Prometheus 查询
        *get_tools_by_package("prometheus"),
        # Loki 日志查询
        *get_tools_by_package("loki"),
    ],
    # 增强功能配置
    "enhanced_features": {
        "enable_rewoo": True,  # 启用 ReWOO 并行采集
        "max_parallel_steps": 10,  # 最大并行步骤数
        "default_timeout": 30.0,  # 默认超时时间（秒）
    }
}

async def enhanced_collect_data(
    user_query: str,
    context: dict = None,
    collected_data: dict = None
) -> dict:
    """
    增强数据采集入口函数

    使用 ReWOO 模式：
    - Planner: 一次性规划所有采集步骤
    - Worker: 并行执行所有采集步骤
    - Solver: 整合结果

    Args:
        user_query: 用户查询
        context: 上下文信息（namespace, filters等）
        collected_data: 已采集的数据（增量采集场景）

    Returns:
        采集和整合后的数据

    示例:
        result = await enhanced_collect_data(
            user_query="检查生产环境的 Pod 状态",
            context={"namespace": "production"},
            collected_data={"pods": [...] if incremental else None
        )
    """


    service = get_enhanced_data_agent_service()
    result = await service.collect_data_rewoo(
        user_query=user_query,
        context=context or {},
        collected_data=collected_data
    )

    return {
        "raw_results": {
            k: {
                "success": v.success,
                "data": v.data if v.success else None,
                "error": v.error,
                "duration": v.duration,
                "source": v.source
            }
            for k, v in result.raw_results.items()
        },
        "processed_data": result.processed_data,
        "summary": result.summary,
        "metadata": result.metadata
    }


__all__ = [
    "DATA_AGENT_CONFIG",
    "enhanced_collect_data",
]
