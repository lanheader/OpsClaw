"""
提示词版本管理数据库模型

存储 Subagents 的基础提示词和 DSPy 优化后的提示词
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean, JSON, Index, ForeignKey
from sqlalchemy.orm import relationship

from app.models.database import Base


class SubagentPrompt(Base):
    """
    Subagent 提示词表

    存储每个 Subagent 的提示词版本
    """
    __tablename__ = "subagent_prompts"

    id = Column(Integer, primary_key=True, index=True)
    subagent_name = Column(String(50), nullable=False, index=True)  # data-agent, analyze-agent, execute-agent
    version = Column(String(50), nullable=False)  # base, v1, v2, latest

    # 提示词内容
    prompt_content = Column(Text, nullable=False)  # 提示词内容
    prompt_type = Column(String(20), nullable=False)  # base, optimized

    # 优化相关
    is_active = Column(Boolean, default=False)  # 是否为当前激活版本
    is_latest = Column(Boolean, default=False)  # 是否为最新版本

    # Few-shot 示例（仅 optimized 类型）
    few_shot_examples = Column(JSON, default=list)  # Few-shot 示例列表

    # 性能指标
    performance_score = Column(Float, default=0.0)  # 性能评分
    usage_count = Column(Integer, default=0)  # 使用次数
    success_rate = Column(Float, default=0.0)  # 成功率

    # 优化元数据（仅 optimized 类型）
    optimization_metadata = Column(JSON, default=dict)  # 优化参数、训练数据量等

    # 审计字段
    created_by = Column(Integer, nullable=True)  # 创建者用户 ID
    updated_by = Column(Integer, nullable=True)  # 更新者用户 ID
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)

    # 备注
    notes = Column(Text, nullable=True)  # 版本说明

    # 创建索引
    __table_args__ = (
        Index('ix_subagent_version_unique', 'subagent_name', 'version', unique=True),
        Index('ix_subagent_active', 'subagent_name', 'is_active'),
        Index('ix_subagent_type', 'subagent_name', 'prompt_type'),
    )

    def __repr__(self):
        return f"<SubagentPrompt(id={self.id}, subagent={self.subagent_name}, version={self.version}, type={self.prompt_type})>"


class PromptChangeLog(Base):
    """
    提示词变更日志表

    记录提示词的修改历史
    """
    __tablename__ = "prompt_change_logs"

    id = Column(Integer, primary_key=True, index=True)

    # 关联信息
    subagent_name = Column(String(50), nullable=False, index=True)
    prompt_id = Column(Integer, ForeignKey('subagent_prompts.id'), nullable=True)

    # 变更信息
    change_type = Column(String(20), nullable=False)  # create, update, optimize, activate
    old_version = Column(String(50), nullable=True)
    new_version = Column(String(50), nullable=False)

    # 变更内容
    old_content = Column(Text, nullable=True)  # 旧内容（前1000字符）
    new_content = Column(Text, nullable=True)  # 新内容（前1000字符）

    # 变更原因
    change_reason = Column(Text, nullable=True)  # 变更原因说明

    # 操作信息
    changed_by = Column(Integer, nullable=True)  # 操作用户 ID
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 优化信息（如果是 optimize 类型）
    optimization_method = Column(String(50), nullable=True)  # DSPy 优化方法
    training_examples_count = Column(Integer, nullable=True)  # 使用的训练数据量

    def __repr__(self):
        return f"<PromptChangeLog(id={self.id}, subagent={self.subagent_name}, type={self.change_type})>"
