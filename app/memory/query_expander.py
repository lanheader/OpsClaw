"""
查询扩展模块 - 用 LLM 将自然语言扩展为关键词组合

弥补纯关键词搜索的语义不足问题。
"""

from typing import Dict
from app.core.llm_factory import LLMFactory
from langchain_core.messages import HumanMessage, SystemMessage
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 缓存（相同查询不重复调用 LLM）
_expand_cache: Dict[str, str] = {}
_MAX_CACHE_SIZE = 200


async def expand_query(user_query: str) -> str:
    """
    用 LLM 把自然语言查询扩展为关键词组合。

    示例：
      "k8s pod crash" → "k8s pod crash OOMKilled CrashLoopBackOff RestartCount"
      "数据库连不上" → "数据库 连接 超时 connection timeout mysql max_connections"

    Args:
        user_query: 用户原始查询

    Returns:
        扩展后的关键词字符串（空格分隔）
    """
    # 命中缓存
    cached = _expand_cache.get(user_query)
    if cached:
        return cached

    try:
        llm = LLMFactory.create_llm()
        resp = await llm.ainvoke([
            SystemMessage(content=(
                "你是运维领域的关键词扩展助手。"
                "将用户的查询扩展为更多相关的搜索关键词，用空格分隔。\n"
                "只输出关键词，不要解释。最多20个词。\n"
                "包括同义词、英文缩写、常见错误名。\n"
                "示例：\n"
                "- pod crash → pod crash OOMKilled CrashLoopBackOff RestartCount\n"
                "- 数据库连不上 → 数据库 连接 超时 connection timeout mysql max_connections\n"
                "- cpu高 → CPU 使用率 负载 load average top进程 oom\n"
                "- 磁盘满了 → 磁盘 满 du df inode no space\n"
            )),
            HumanMessage(content=user_query),
        ])
        expanded = resp.content.strip()
        logger.debug(f"🔑 查询扩展: '{user_query[:30]}' → '{expanded[:60]}'")
    except Exception as e:
        logger.warning(f"⚠️ 查询扩展失败，使用原始查询: {e}")
        expanded = user_query

    # 写入缓存
    _expand_cache[user_query] = expanded

    # 限制缓存大小
    if len(_expand_cache) > _MAX_CACHE_SIZE:
        keys_to_remove = list(_expand_cache.keys())[:_MAX_CACHE_SIZE // 2]
        for k in keys_to_remove:
            del _expand_cache[k]

    return expanded


__all__ = ["expand_query"]
