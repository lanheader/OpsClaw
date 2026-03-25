"""
Analyze Agent - 分析决策子智能体

增强版：组合 ReAct + ToT + Self-Reflection + RAG 模式

功能：
1. 分析采集的数据，诊断问题根因
2. 使用 ToT 模式探索多个诊断路径
3. 自我反思和验证诊断结果
4. 基于 RAG 检索历史案例增强诊断
5. 生成修复建议

v3.2 变更：
- 增加增强分析服务支持
- 增加 K8s 读工具，用于验证分析结论
- 支持 ToT 多路径诊断
- 支持 Self-Reflection 自我验证
- 支持 RAG 知识库增强
⭐ system_prompt 将动态从数据库加载
"""

from app.tools import get_tools_by_group
from app.services.enhanced_analyze_service import get_enhanced_analyze_service

# 基础配置
ANALYZE_AGENT_CONFIG = {
    "name": "analyze-agent",
    "description": "分析采集的数据,诊断问题根因,生成修复建议（支持 ToT、Self-Reflection、RAG）",
    "system_prompt": None,  # 将动态从数据库加载
    "tools": [
        # 增加读工具：用于验证分析结论
        *get_tools_by_group("k8s.read"),
    ],
    # 增强功能配置
    "enhanced_features": {
        "enable_tot": True,  # 启用 ToT 多路径诊断
        "enable_reflection": True,  # 启用 Self-Reflection
        "enable_rag": True,  # 启用 RAG 知识库增强
        "max_diagnosis_paths": 3,  # 最大诊断路径数
        "max_depth_per_path": 3,  # 每条路径最大深度
    }
}

async def enhanced_diagnose(
    user_query: str,
    collected_data: dict,
    context: dict = None,
    **kwargs
) -> dict:
    """
    增强诊断入口函数

    组合使用：
    - ToT: 多路径诊断探索
    - Self-Reflection: 自我评估与验证
    - RAG: 基于历史案例的增强

    Args:
        user_query: 用户查询
        collected_data: 采集的数据
        context: 上下文信息
        **kwargs: 其他参数

    Returns:
        诊断结果字典
    """


    service = get_enhanced_analyze_service()
    result = await service.diagnose(
        user_query=user_query,
        collected_data=collected_data,
        context=context or {},
        **kwargs
    )

    return {
        "root_cause": result.root_cause,
        "confidence": result.confidence,
        "severity": result.severity,
        "recommendations": result.recommendations,
        "reasoning_chain": result.reasoning_chain,
        "referenced_cases": result.referenced_cases,
        "alternative_paths": [
            {
                "hypothesis": p.hypothesis.description,
                "confidence": p.final_confidence,
                "conclusion": p.conclusion
            }
            for p in result.alternative_paths[:3]  # 最多显示3个替代路径
        ]
    }


__all__ = [
    "ANALYZE_AGENT_CONFIG",
    "enhanced_diagnose",
]
