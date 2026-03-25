"""
统一提示词服务

直接从静态文件加载提示词
"""

import logging
from typing import Optional, Dict
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


class UnifiedPromptOptimizer:
    """
    统一提示词服务

    功能：
    - 从静态文件加载提示词
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
        """
        # 1. 检查缓存
        cached = self._get_from_cache(subagent_name)
        if cached:
            return cached

        # 2. 从静态文件加载
        prompt = self._load_static_prompt(subagent_name)
        self._set_cache(subagent_name, prompt)
        return prompt

    def _load_static_prompt(self, subagent_name: str) -> str:
        """从静态文件加载提示词"""
        # 导入静态提示词
        if subagent_name == "data-agent":
            from app.prompts.subagents.data import DATA_AGENT_PROMPT
            return DATA_AGENT_PROMPT
        elif subagent_name == "analyze-agent":
            from app.prompts.subagents.analyze import ANALYZE_AGENT_PROMPT
            return ANALYZE_AGENT_PROMPT
        elif subagent_name == "execute-agent":
            from app.prompts.subagents.execute import EXECUTE_AGENT_PROMPT
            return EXECUTE_AGENT_PROMPT
        elif subagent_name == "main-agent":
            from app.prompts.main_agent import MAIN_AGENT_SYSTEM_PROMPT
            return MAIN_AGENT_SYSTEM_PROMPT
        else:
            logger.warning(f"未知的 subagent: {subagent_name}，返回空提示词")
            return ""

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
        else:
            self._cache.clear()


# ============== 全局实例 ==============

_optimizer_instance: Optional[UnifiedPromptOptimizer] = None


def get_prompt_optimizer() -> UnifiedPromptOptimizer:
    """获取统一提示词服务单例"""
    global _optimizer_instance
    if _optimizer_instance is None:
        _optimizer_instance = UnifiedPromptOptimizer()
    return _optimizer_instance
