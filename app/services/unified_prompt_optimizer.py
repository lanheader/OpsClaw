"""
统一提示词服务

从数据库加载提示词，支持缓存
"""

import logging
from typing import Optional, Dict
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


class UnifiedPromptOptimizer:
    """
    统一提示词服务

    功能：
    - 从数据库加载提示词
    - 缓存提示词
    """

    # 缓存配置
    CACHE_TTL_SECONDS = 3600 * 24  # 缓存 24 小时
    _cache: Dict[str, Dict] = {}

    def get_prompt_for_agent(self, subagent_name: str) -> str:
        """
        为 Agent 获取提示词

        Args:
            subagent_name: 子智能体名称

        Returns:
            提示词内容

        Raises:
            ValueError: 提示词不存在时抛出
        """
        # 1. 检查缓存
        cached = self._get_from_cache(subagent_name)
        if cached:
            logger.debug(f"✅ 从缓存加载提示词: {subagent_name}")
            return cached

        # 2. 从数据库加载
        prompt = self._load_from_database(subagent_name)
        if prompt:
            self._set_cache(subagent_name, prompt)
            return prompt

        # 3. 未找到提示词
        logger.error(f"❌ 数据库中未找到提示词: {subagent_name}")
        raise ValueError(f"提示词不存在: {subagent_name}，请先在提示词管理页面添加")

    def _load_from_database(self, subagent_name: str) -> Optional[str]:
        """从数据库加载提示词"""
        try:
            from app.models.database import SessionLocal
            from app.models.agent_prompt import AgentPrompt

            db = SessionLocal()
            try:
                prompt = db.query(AgentPrompt).filter(
                    AgentPrompt.agent_name == subagent_name,
                    AgentPrompt.is_active == True
                ).first()

                if prompt:
                    logger.info(f"✅ 从数据库加载提示词: {subagent_name} (version {prompt.version})")
                    return prompt.content
            finally:
                db.close()
        except Exception as e:
            logger.error(f"❌ 从数据库加载提示词失败: {subagent_name}, error: {e}")

        return None

    def _get_from_cache(self, subagent_name: str) -> Optional[str]:
        """从缓存获取"""
        cached = self._cache.get(subagent_name)
        if cached:
            # 检查是否过期
            if datetime.now(timezone.utc) - cached["timestamp"] < timedelta(seconds=self.CACHE_TTL_SECONDS):
                return cached["prompt"]
            else:
                # 缓存过期，删除
                del self._cache[subagent_name]
        return None

    def _set_cache(self, subagent_name: str, prompt: str):
        """设置缓存"""
        self._cache[subagent_name] = {
            "prompt": prompt,
            "timestamp": datetime.now(timezone.utc),
        }

    def clear_cache(self, subagent_name: Optional[str] = None):
        """清除缓存"""
        if subagent_name:
            self._cache.pop(subagent_name, None)
            logger.info(f"🗑️ 已清除提示词缓存: {subagent_name}")
        else:
            self._cache.clear()
            logger.info("🗑️ 已清除所有提示词缓存")


_optimizer_instance: Optional[UnifiedPromptOptimizer] = None


def get_prompt_optimizer() -> UnifiedPromptOptimizer:
    """获取统一提示词服务单例"""
    global _optimizer_instance
    if _optimizer_instance is None:
        _optimizer_instance = UnifiedPromptOptimizer()
    return _optimizer_instance
