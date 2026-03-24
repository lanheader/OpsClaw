"""
统一提示词优化服务

这是唯一的提示词优化入口，整合了以下功能：
1. 从数据库读取基础提示词（Web 可编辑）
2. 使用 DSPy KNN 进行实时优化
3. 自动收集训练数据
4. 自动触发优化（达到阈值时）
5. 缓存优化结果

数据流：
  数据库 (subagent_prompts)
    → 基础提示词 (prompt_type='base')
    → 优化提示词 (prompt_type='optimized')
  数据库 (training_examples)
    → 训练数据收集
"""

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from pathlib import Path
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.subagent_prompt import SubagentPrompt
from app.models.dspy_prompt import TrainingExample, PromptOptimizationLog
from app.services.prompt_management import PromptManagementService

logger = logging.getLogger(__name__)


# 自动优化配置
AUTO_OPTIMIZE_CONFIG = {
    "min_examples_for_optimization": 5,
    "optimal_examples_count": 10,
    "min_optimization_interval_hours": 1,
    "max_labeled_demos": 5,
    "max_rounds": 3,
}


class UnifiedPromptOptimizer:
    """
    统一提示词优化器

    这是唯一的提示词优化入口，整合了所有优化功能：
    - 为 Agent 获取优化后的提示词
    - 自动收集训练数据
    - 自动触发优化
    - 缓存优化结果
    """

    # 缓存配置
    CACHE_TTL_SECONDS = 3600  # 缓存 1 小时
    _cache: Dict[str, Dict] = {}

    def __init__(self):
        self.management = PromptManagementService()

    def get_prompt_for_agent(self, subagent_name: str) -> str:
        """
        为 Agent 获取优化后的提示词（主入口）

        流程：
        1. 检查缓存
        2. 从数据库获取基础提示词
        3. 检查是否有有效的优化版本
        4. 如果需要，运行 DSPy 优化
        5. 返回优化后的提示词

        Args:
            subagent_name: 子智能体名称

        Returns:
            优化后的提示词
        """
        # 1. 检查缓存
        cached = self._get_from_cache(subagent_name)
        if cached:
            logger.info(f"🎯 {subagent_name} 使用缓存的优化提示词")
            return cached

        # 2. 从数据库获取基础提示词
        db = next(get_db())
        try:
            base_prompt = self.management.get_base_prompt(subagent_name, db)

            if not base_prompt:
                # 如果数据库没有，初始化基础提示词
                logger.warning(f"{subagent_name} 数据库中没有基础提示词，正在初始化...")
                self.management.initialize_base_prompts()
                base_prompt = self.management.get_base_prompt(subagent_name, db)

            if not base_prompt:
                # 如果还是没有，使用静态文件回退
                logger.warning(f"{subagent_name} 无法从数据库加载，使用静态文件回退")
                return self._load_static_prompt(subagent_name)

            # 3. 尝试获取最新的优化版本
            optimized = (
                db.query(SubagentPrompt)
                .filter(
                    and_(
                        SubagentPrompt.subagent_name == subagent_name,
                        SubagentPrompt.prompt_type == "optimized",
                        SubagentPrompt.is_latest == True,
                    )
                )
                .first()
            )

            # 4. 判断是否需要重新优化
            need_reoptimize = False

            if not optimized:
                logger.info(f"🆕 {subagent_name} 尚无优化版本，开始优化...")
                need_reoptimize = True
            else:
                # 基础提示词更新后需要重新优化
                if base_prompt.updated_at > optimized.created_at:
                    logger.info(f"🔄 {subagent_name} 基础提示词已被 Web 修改，重新优化...")
                    need_reoptimize = True
                # 优化版本超过 1 小时
                elif optimized.created_at < datetime.utcnow() - timedelta(hours=1):
                    logger.info(f"🔄 {subagent_name} 优化版本已过期（超过 1 小时），重新优化...")
                    need_reoptimize = True
                else:
                    # 使用已有版本
                    logger.info(f"✅ {subagent_name} 使用已有的优化版本 (v{optimized.version})")
                    prompt = optimized.prompt_content
                    self._update_usage_stats(optimized)
                    self._set_cache(subagent_name, prompt)
                    return prompt

            # 5. 执行优化
            if need_reoptimize:
                prompt = self._run_dspy_optimization(subagent_name, base_prompt.prompt_content)
                self._set_cache(subagent_name, prompt)
                return prompt

        finally:
            db.close()

    def _load_static_prompt(self, subagent_name: str) -> str:
        """从静态文件加载提示词（回退方案）"""
        return self.management._import_static_prompt(subagent_name)

    def _run_dspy_optimization(self, subagent_name: str, base_prompt: str) -> str:
        """
        运行 DSPy 优化

        Args:
            subagent_name: 子智能体名称
            base_prompt: 从数据库读取的基础提示词

        Returns:
            优化后的提示词
        """
        try:
            import dspy
            from app.dspy.llm_adapter import create_dspy_llm_for_subagent
            from app.dspy.modules import DataModule, AnalyzeModule, ExecuteModule

            # 检查 DSPy 是否可用
            if not dspy:
                logger.warning(f"DSPy 不可用，{subagent_name} 使用基础提示词")
                return base_prompt

            # 1. 配置 DSPy LLM
            dspy_llm = create_dspy_llm_for_subagent(subagent_name)
            dspy.settings.configure(lm=dspy_llm)

            # 2. 获取训练数据
            db = next(get_db())
            try:
                examples = (
                    db.query(TrainingExample)
                    .filter(
                        and_(
                            TrainingExample.subagent_name == subagent_name,
                            TrainingExample.quality_score >= 0.6,
                        )
                    )
                    .order_by(TrainingExample.quality_score.desc())
                    .limit(10)
                    .all()
                )
            finally:
                db.close()

            # 3. 创建对应的 DSPy 模块
            modules = {
                "data-agent": DataModule,
                "analyze-agent": AnalyzeModule,
                "execute-agent": ExecuteModule,
            }
            module_class = modules.get(subagent_name)
            if not module_class:
                return base_prompt

            # 4. 使用 DSPy 编译（如果有训练数据）
            if examples and len(examples) >= 3:
                try:
                    # 转换训练数据为 DSPy 格式
                    dspy_examples = []
                    for ex in examples[:5]:  # 最多使用 5 个示例
                        dspy_examples.append(
                            dspy.Example(
                                task_description=ex.user_input,
                                reasoning=ex.agent_output,
                            ).with_inputs("task_description")
                        )

                    # 使用 BootstrapFewShot 优化器（DSPy 3.x 标准）
                    from dspy.teleprompt import BootstrapFewShot

                    # 定义简单的评估指标
                    def exact_match_metric(gold, pred, trace=None):
                        return gold.reasoning.lower() == pred.reasoning.lower()

                    teleprompter = BootstrapFewShot(
                        metric=exact_match_metric,
                        max_labeled_demos=3,
                        max_rounds=1
                    )
                    compiled = teleprompter.compile(module_class(), trainset=dspy_examples)

                    # 提取编译后的提示词（包含 demos）
                    prompt = self._build_optimized_prompt(base_prompt, compiled)
                    logger.info(f"✅ {subagent_name} DSPy 优化完成（使用 {len(dspy_examples)} 个示例）")

                    # 保存到数据库
                    self._save_optimized_to_db(subagent_name, prompt, len(examples))

                    return prompt

                except Exception as e:
                    logger.warning(f"{subagent_name} DSPy 优化失败: {e}，使用基础提示词")
                    return base_prompt
            else:
                # 没有足够的训练数据，直接使用基础提示词
                logger.info(f"{subagent_name} 训练数据不足（{len(examples)}/3），使用基础提示词")
                return base_prompt

        except ImportError:
            logger.warning(f"DSPy 未安装，{subagent_name} 使用基础提示词")
            return base_prompt
        except Exception as e:
            logger.error(f"{subagent_name} 优化过程出错: {e}")
            return base_prompt

    def _build_optimized_prompt(self, base_prompt: str, compiled_module) -> str:
        """从编译的模块构建优化提示词"""
        parts = [base_prompt.strip()]

        if hasattr(compiled_module, 'demos') and compiled_module.demos:
            parts.append("\n\n=== DSPy 优化示例 ===\n")
            for i, demo in enumerate(compiled_module.demos[:5], 1):
                if hasattr(demo, '__dict__'):
                    demo_dict = demo.__dict__
                    if 'task_description' in demo_dict:
                        parts.append(f"\n<!-- 示例 {i} -->")
                        parts.append(f"输入: {demo_dict['task_description']}")
                        if hasattr(demo, 'reasoning') and demo.reasoning:
                            parts.append(f"输出: {demo.reasoning}")

        return "\n".join(parts)

    def _save_optimized_to_db(self, subagent_name: str, optimized_prompt: str, examples_count: int):
        """保存优化结果到数据库"""
        db = next(get_db())
        try:
            # 将旧版本的 is_latest 设为 False
            db.query(SubagentPrompt).filter(
                and_(
                    SubagentPrompt.subagent_name == subagent_name,
                    SubagentPrompt.prompt_type == "optimized",
                )
            ).update({"is_latest": False})

            # 生成版本号
            latest_count = (
                db.query(SubagentPrompt)
                .filter(
                    and_(
                        SubagentPrompt.subagent_name == subagent_name,
                        SubagentPrompt.prompt_type == "optimized",
                    )
                )
                .count()
            )
            version = f"v{latest_count + 1}"

            # 创建新版本
            new_prompt = SubagentPrompt(
                subagent_name=subagent_name,
                version=version,
                prompt_content=optimized_prompt,
                prompt_type="optimized",
                is_active=True,
                is_latest=True,
                optimization_metadata={
                    "method": "knn",
                    "training_examples_count": examples_count,
                    "created_at": datetime.utcnow().isoformat(),
                },
            )

            db.add(new_prompt)
            db.commit()

            logger.info(f"✅ {subagent_name} 优化提示词已保存到数据库 (版本: {version})")

        finally:
            db.close()

    def _update_usage_stats(self, prompt: SubagentPrompt):
        """更新提示词使用统计"""
        prompt.usage_count += 1
        prompt.last_used_at = datetime.utcnow()

    def _get_from_cache(self, subagent_name: str) -> Optional[str]:
        """从缓存获取"""
        cached = self._cache.get(subagent_name)
        if cached:
            # 检查是否过期
            if datetime.utcnow() - cached["timestamp"] < timedelta(seconds=self.CACHE_TTL_SECONDS):
                return cached["prompt"]
            else:
                # 缓存过期，删除
                del self._cache[subagent_name]
        return None

    def _set_cache(self, subagent_name: str, prompt: str):
        """设置缓存"""
        self._cache[subagent_name] = {
            "prompt": prompt,
            "timestamp": datetime.utcnow(),
        }

    def clear_cache(self, subagent_name: Optional[str] = None):
        """清除缓存"""
        if subagent_name:
            self._cache.pop(subagent_name, None)
        else:
            self._cache.clear()

    async def collect_training_example(
        self,
        subagent_name: str,
        user_input: str,
        agent_output: str,
        context: Dict[str, Any],
        example_type: str,
        session_id: Optional[str] = None,
        user_id: Optional[int] = None,
        quality_score: float = 0.7,
    ) -> TrainingExample:
        """
        收集训练示例（在每次用户交互后调用）

        Args:
            subagent_name: 子智能体名称
            user_input: 用户输入
            agent_output: Agent 输出
            context: 上下文信息（工具调用、中间结果等）
            example_type: 示例类型 (query, diagnose, execute)
            session_id: 会话 ID
            user_id: 用户 ID
            quality_score: 质量评分 (0-1)

        Returns:
            创建的训练示例
        """
        db = next(get_db())
        try:
            example = TrainingExample(
                subagent_name=subagent_name,
                user_input=user_input,
                agent_output=agent_output,
                context=context,
                example_type=example_type,
                session_id=session_id,
                user_id=user_id,
                quality_score=quality_score,
            )

            db.add(example)
            db.commit()
            db.refresh(example)

            logger.info(
                f"收集训练示例: {subagent_name} | "
                f"type={example_type} | quality={quality_score:.2f}"
            )

            # 检查是否需要触发自动优化
            await self._check_and_trigger_auto_optimize(subagent_name)

            return example

        except Exception as e:
            logger.error(f"收集训练示例时出错: {e}")
            db.rollback()
            raise
        finally:
            db.close()

    async def _check_and_trigger_auto_optimize(self, subagent_name: str):
        """
        检查是否满足自动优化条件，如果满足则触发优化

        条件：
        1. 未使用的训练示例数量 >= min_examples_for_optimization
        2. 距离上次优化时间 >= min_optimization_interval_hours
        """
        db = next(get_db())
        try:
            # 1. 检查未使用的训练示例数量
            unused_count = (
                db.query(TrainingExample)
                .filter(
                    and_(
                        TrainingExample.subagent_name == subagent_name,
                        TrainingExample.is_used_for_optimization == False,
                        TrainingExample.quality_score >= 0.6,
                    )
                )
                .count()
            )

            if unused_count < AUTO_OPTIMIZE_CONFIG["min_examples_for_optimization"]:
                logger.debug(
                    f"{subagent_name}: 训练示例不足 ({unused_count}/{AUTO_OPTIMIZE_CONFIG['min_examples_for_optimization']})"
                )
                return

            # 2. 检查距离上次优化时间
            last_optimization = (
                db.query(PromptOptimizationLog)
                .filter(
                    and_(
                        PromptOptimizationLog.subagent_name == subagent_name,
                        PromptOptimizationLog.status == "success",
                    )
                )
                .order_by(PromptOptimizationLog.completed_at.desc())
                .first()
            )

            if last_optimization and last_optimization.completed_at:
                elapsed = datetime.utcnow() - last_optimization.completed_at
                if elapsed < timedelta(hours=AUTO_OPTIMIZE_CONFIG["min_optimization_interval_hours"]):
                    logger.debug(
                        f"{subagent_name}: 距离上次优化时间不足 "
                        f"({elapsed.total_seconds()/3600:.1f}h < {AUTO_OPTIMIZE_CONFIG['min_optimization_interval_hours']}h)"
                    )
                    return

            # 3. 触发自动优化
            logger.info(f"🚀 触发自动优化: {subagent_name} (未使用示例: {unused_count})")
            await self.optimize_and_store(subagent_name, trigger_type="auto")

        except Exception as e:
            logger.error(f"检查自动优化条件时出错: {e}")
        finally:
            db.close()

    async def optimize_and_store(
        self,
        subagent_name: str,
        trigger_type: str = "manual",
        trigger_reason: Optional[str] = None,
    ) -> PromptOptimizationLog:
        """
        执行优化并存储到数据库

        Args:
            subagent_name: 子智能体名称
            trigger_type: 触发类型 (manual, auto, scheduled)
            trigger_reason: 触发原因

        Returns:
            优化日志
        """
        db = next(get_db())
        log = PromptOptimizationLog(
            subagent_name=subagent_name,
            trigger_type=trigger_type,
            trigger_reason=trigger_reason,
            optimization_method="knn",
            started_at=datetime.utcnow(),
            status="running",
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        try:
            logger.info(f"开始优化 {subagent_name} 的提示词...")

            # 1. 获取基础提示词
            base_prompt = self.management.get_base_prompt(subagent_name, db)
            if not base_prompt:
                raise ValueError(f"{subagent_name} 没有基础提示词")

            # 2. 收集训练数据
            examples = (
                db.query(TrainingExample)
                .filter(
                    and_(
                        TrainingExample.subagent_name == subagent_name,
                        TrainingExample.quality_score >= 0.6,
                    )
                )
                .order_by(TrainingExample.quality_score.desc())
                .limit(AUTO_OPTIMIZE_CONFIG["optimal_examples_count"])
                .all()
            )

            logger.info(f"收集到 {len(examples)} 个训练示例")

            if not examples:
                raise ValueError("没有可用的训练示例")

            # 3. 执行 DSPy 优化
            optimized_prompt = self._run_dspy_optimization(subagent_name, base_prompt.prompt_content)

            # 4. 更新日志
            log.status = "success"
            log.new_version = db.query(SubagentPrompt).filter(
                and_(
                    SubagentPrompt.subagent_name == subagent_name,
                    SubagentPrompt.prompt_type == "optimized",
                    SubagentPrompt.is_latest == True,
                )
            ).first().version
            log.training_examples_count = len(examples)
            log.completed_at = datetime.utcnow()
            log.duration_seconds = (log.completed_at - log.started_at).total_seconds()
            log.optimization_metrics = {
                "examples_used": len(examples),
                "prompt_length": len(optimized_prompt),
            }

            # 5. 标记训练示例已使用
            example_ids = [ex.id for ex in examples]
            db.query(TrainingExample).filter(
                TrainingExample.id.in_(example_ids)
            ).update({
                "is_used_for_optimization": True,
                "used_in_prompt_version": log.new_version,
            })

            db.commit()

            logger.info(f"✅ {subagent_name} 提示词优化完成 (版本: {log.new_version})")

            return log

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)
            log.completed_at = datetime.utcnow()
            log.duration_seconds = (log.completed_at - log.started_at).total_seconds()
            db.commit()

            logger.error(f"优化 {subagent_name} 时出错: {e}")
            raise
        finally:
            db.close()


# ============== 全局实例 ==============

_optimizer_instance: Optional[UnifiedPromptOptimizer] = None


def get_prompt_optimizer() -> UnifiedPromptOptimizer:
    """获取统一提示词优化器单例"""
    global _optimizer_instance
    if _optimizer_instance is None:
        _optimizer_instance = UnifiedPromptOptimizer()
    return _optimizer_instance


# ============== 便捷函数 ==============

async def collect_interaction_for_training(
    subagent_name: str,
    user_input: str,
    agent_output: str,
    context: Dict[str, Any],
    example_type: str,
    session_id: Optional[str] = None,
    user_id: Optional[int] = None,
) -> TrainingExample:
    """
    收集用户交互用于训练（在每次用户交互后调用）

    这是主要的入口函数，在 chat_service 中调用

    Args:
        subagent_name: 子智能体名称
        user_input: 用户输入
        agent_output: Agent 输出
        context: 上下文信息
        example_type: 示例类型
        session_id: 会话 ID
        user_id: 用户 ID

    Returns:
        创建的训练示例
    """
    optimizer = get_prompt_optimizer()
    return await optimizer.collect_training_example(
        subagent_name=subagent_name,
        user_input=user_input,
        agent_output=agent_output,
        context=context,
        example_type=example_type,
        session_id=session_id,
        user_id=user_id,
    )


async def trigger_manual_optimization(subagent_name: str) -> PromptOptimizationLog:
    """
    手动触发优化

    Args:
        subagent_name: 子智能体名称

    Returns:
        优化日志
    """
    optimizer = get_prompt_optimizer()
    return await optimizer.optimize_and_store(
        subagent_name=subagent_name,
        trigger_type="manual",
        trigger_reason="用户手动触发",
    )
