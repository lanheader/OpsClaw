"""
Execute Agent - 执行操作子智能体

增强版：使用 ReAct + Self-Reflection + 回滚机制

功能：
1. 执行前风险评估
2. ReAct 循环执行
3. 执行后验证
4. 失败自动回滚

⭐ system_prompt 将动态从数据库加载
"""

from app.tools import get_tools_by_group
from app.services.enhanced_execute_service import get_enhanced_execute_service

# 基础配置
EXECUTE_AGENT_CONFIG = {
    "name": "execute-agent",
    "description": "执行修复命令,监控执行结果（支持风险评估、执行验证、自动回滚）",
    "system_prompt": None,  # 将动态从数据库加载
    "tools": [
        # K8s 写操作和删除操作工具
        *get_tools_by_group("k8s.write"),
        *get_tools_by_group("k8s.delete"),
        *get_tools_by_group("k8s.update"),
        # 增加读工具：用于验证执行结果
        *get_tools_by_group("k8s.read"),
    ],
    # 增强功能配置
    "enhanced_features": {
        "enable_react": True,  # 启用 ReAct 循环
        "enable_self_reflection": True,  # 启用自我评估
        "auto_rollback": True,  # 自动回滚
        "risk_assessment": True,  # 风险评估
        "require_approval_for_high_risk": True,  # 高风险操作需要批准
    }
}


# ==================== 增强执行入口 ====================

async def enhanced_execute_remediation(
    user_query: str,
    remediation_plan: list,
    context: dict = None,
    auto_rollback: bool = True
) -> dict:
    """
    增强执行入口函数

    安全执行修复操作：
    - 风险评估
    - ReAct 循环执行
    - 执行后验证
    - 失败自动回滚

    Args:
        user_query: 用户查询
        remediation_plan: 修复计划步骤列表
        context: 上下文信息
        auto_rollback: 是否自动回滚

    Returns:
        执行结果

    示例:
        result = await enhanced_execute_remediation(
            user_query="重启失败的 Pod",
            remediation_plan=[
                "kubectl delete pod user-service-xxx -n production",
                "验证 Pod 重新启动成功"
            ],
            context={"namespace": "production"}
        )
    """


    service = get_enhanced_execute_service()
    result = await service.execute_with_safety(
        user_query=user_query,
        remediation_plan=remediation_plan,
        context=context or {},
        auto_rollback=auto_rollback
    )

    return {
        "status": result.status.value,
        "steps_results": [
            {
                "step_id": r.step_id,
                "success": r.success,
                "output": r.output,
                "error": r.error,
                "duration": r.duration,
                "verified": r.verified
            }
            for r in result.steps_results
        ],
        "final_output": result.final_output,
        "error": result.error,
        "total_duration": result.total_duration,
        "rollback_performed": result.rollback_performed,
        "rollback_details": result.rollback_details,
        "verification_results": result.verification_results
    }


__all__ = [
    "EXECUTE_AGENT_CONFIG",
    "enhanced_execute_remediation",
]

