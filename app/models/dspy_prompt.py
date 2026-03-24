"""
DSPy 训练数据和优化日志数据库模型

注意：优化后的提示词统一存储在 subagent_prompts 表中（prompt_type='optimized'）
此模块只保留训练示例和优化日志
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean, JSON, Index

from app.models.database import Base


class TrainingExample(Base):
    """
    训练示例表

    存储用于 DSPy 优化的训练数据（用户输入 + AI 输出）
    """
    __tablename__ = "training_examples"

    id = Column(Integer, primary_key=True, index=True)

    # 关联信息
    session_id = Column(String(100), nullable=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)

    # Subagent 关联
    subagent_name = Column(String(50), nullable=False, index=True)

    # 示例内容
    user_input = Column(Text, nullable=False)  # 用户输入
    agent_output = Column(Text, nullable=False)  # Agent 输出
    context = Column(JSON, default=dict)  # 上下文信息（工具调用、中间结果等）

    # 分类和评分
    example_type = Column(String(20), nullable=False)  # query, diagnose, execute
    quality_score = Column(Float, default=0.5)  # 质量评分 (0-1)

    # 优化状态
    is_used_for_optimization = Column(Boolean, default=False)  # 是否已用于优化
    used_in_prompt_version = Column(String(50), nullable=True)  # 用于哪个版本的提示词

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 创建索引
    __table_args__ = (
        Index('ix_subagent_type', 'subagent_name', 'example_type'),
        Index('ix_subagent_quality', 'subagent_name', 'quality_score'),
        Index('ix_used_for_opt', 'subagent_name', 'is_used_for_optimization'),
    )

    def __repr__(self):
        return f"<TrainingExample(id={self.id}, subagent={self.subagent_name}, type={self.example_type})>"


class PromptOptimizationLog(Base):
    """
    提示词优化日志表

    记录每次提示词优化的详细信息
    """
    __tablename__ = "prompt_optimization_logs"

    id = Column(Integer, primary_key=True, index=True)

    # 优化目标
    subagent_name = Column(String(50), nullable=False, index=True)
    old_prompt_id = Column(Integer, nullable=True)  # 旧提示词 ID
    new_prompt_id = Column(Integer, nullable=True)  # 新提示词 ID (优化完成后填充)
    new_version = Column(String(50), nullable=True)  # 新版本号 (优化完成后填充)

    # 优化参数
    optimization_method = Column(String(50), nullable=False)
    training_examples_count = Column(Integer, default=0)
    max_labeled_demos = Column(Integer, default=5)
    max_rounds = Column(Integer, default=3)

    # 优化结果
    status = Column(String(20), nullable=False)  # success, failed, partial
    error_message = Column(Text, nullable=True)
    optimization_metrics = Column(JSON, default=dict)

    # 触发信息
    trigger_type = Column(String(20), nullable=False)  # manual, auto, scheduled
    trigger_reason = Column(Text, nullable=True)

    # 时间戳
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    def __repr__(self):
        return f"<PromptOptimizationLog(id={self.id}, subagent={self.subagent_name}, status={self.status})>"
