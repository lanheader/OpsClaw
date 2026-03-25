"""
核心常量和枚举定义

定义系统使用的常量、枚举和配置
"""

from enum import Enum
from typing import List


# ==================== 严重程度枚举 ====================

class Severity(str, Enum):
    """严重程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ==================== 任务状态枚举 ====================

class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ==================== 风险等级枚举 ====================

class RiskLevel(str, Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ==================== 关键词常量 ====================

class AnalysisKeywords(str, Enum):
    """分析关键词"""
    CONCLUSION = "结论"
    SUGGESTION = "建议"
    RECOMMENDATION = "建议"
    CAUSE = "原因"
    ROOT_CAUSE = "根因"
    RESULT = "结果"
    FINDING = "发现"
    DIAGNOSIS = "诊断"


# 用于快速检查的关键词列表
ANALYSIS_KEYWORDS_LIST = [kw.value for kw in AnalysisKeywords]

# 用于句子分析的关键词组合
SENTENCE_ANALYSIS_KEYWORDS = [
    AnalysisKeywords.CONCLUSION.value,
    AnalysisKeywords.SUGGESTION.value,
    AnalysisKeywords.CAUSE.value,
]


# ==================== 故障处理关键词 ====================

class IncidentKeywords(str, Enum):
    """故障处理关键词"""
    ALERT = "告警"
    ANOMALY = "异常"
    ERROR = "错误"
    FAILURE = "故障"
    TROUBLESHOOT = "排查"
    DIAGNOSE = "诊断"
    FIX = "修复"
    RESTART = "重启"


# 用于快速检查是否是故障处理
INCIDENT_KEYWORDS_LIST = [kw.value for kw in IncidentKeywords]


# ==================== 中间件配置 ====================

class MiddlewareConfig:
    """中间件配置"""

    # 上下文压缩配置
    COMPRESSION_THRESHOLD = 30  # 超过此消息数时触发压缩
    MAX_FULL_MESSAGES = 20      # 保留的最近完整消息数
    SUMMARY_BLOCK_SIZE = 10     # 每 N 条消息生成一个摘要

    # 消息截断配置
    MAX_MESSAGES_TO_KEEP = 40   # 保留最近的消息数
    MIN_MESSAGES_TO_KEEP = 10   # 最少保留的消息数

    # 历史记录限制（防止内存泄漏）
    MAX_HISTORY_SIZE = 1000     # 最大历史记录数


# ==================== 向量存储配置 ====================

class VectorStoreConfig:
    """向量存储配置"""

    # 搜索限制
    MAX_SEARCH_RESULTS = 100    # 最大搜索结果数
    SIMILARITY_THRESHOLD = 0.7  # 默认相似度阈值

    # 向量维度
    EMBEDDING_DIMENSION = 1536  # OpenAI text-embedding-3-small


# ==================== LLM 调用配置 ====================

class LLMConfig:
    """LLM 调用配置"""

    # 默认超时时间
    DEFAULT_TIMEOUT = 30.0

    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0

    # Token 限制
    MAX_TOKENS = 4096
    TEMPERATURE = 0.7


# ==================== 辅助函数 ====================

def is_incident_handling(query: str) -> bool:
    """判断查询是否与故障处理相关"""
    query_lower = query.lower()
    return any(kw in query_lower for kw in INCIDENT_KEYWORDS_LIST)


def has_analysis_keywords(content: str) -> bool:
    """判断内容是否包含分析关键词"""
    return any(kw in content for kw in ANALYSIS_KEYWORDS_LIST)


__all__ = [
    # 枚举
    "Severity",
    "TaskStatus",
    "RiskLevel",
    "AnalysisKeywords",
    "IncidentKeywords",
    # 关键词列表
    "ANALYSIS_KEYWORDS_LIST",
    "INCIDENT_KEYWORDS_LIST",
    "SENTENCE_ANALYSIS_KEYWORDS",
    # 配置类
    "MiddlewareConfig",
    "VectorStoreConfig",
    "LLMConfig",
    # 辅助函数
    "is_incident_handling",
    "has_analysis_keywords",
]
