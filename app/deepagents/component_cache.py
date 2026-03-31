"""
Agent 组件缓存

缓存 Agent 的组件（工具、Subagent、中间件），避免每次请求都重新加载。
权限过滤在创建 Agent 时进行，保证权限动态生效。

缓存策略：
- Subagent：全局缓存（不涉及权限）
- 中间件：全局缓存（不涉及权限）
- 工具：按权限组合缓存（权限变更时自动更新）

权限变更处理：
- 当权限配置变更时，调用 invalidate_tools_cache() 清除工具缓存
- 下次请求时会根据新权限重新加载工具
"""

from typing import Dict, List, Optional, Set, Any, FrozenSet

from app.utils.logger import get_logger
from app.deepagents.subagents import get_all_subagents
from app.tools.registry import get_tool_registry
from app.middleware.error_filtering_middleware import ErrorFilteringMiddleware
from app.middleware.logging_middleware import LoggingMiddleware

logger = get_logger(__name__)


class ComponentCache:
    """
    Agent 组件缓存管理器

    缓存内容：
    1. Subagent 列表（全局，不涉及权限）
    2. 中间件列表（全局，不涉及权限）
    3. 工具列表（按权限组合缓存）

    不缓存的内容：
    - Agent 图实例（必须每次创建，保证权限动态生效）
    - Checkpointer（全局单例，由 checkpointer.py 管理）
    """

    # ========== 缓存存储 ==========

    # Subagent 缓存（全局）
    _subagents_cache: Optional[List[Dict[str, Any]]] = None

    # 中间件缓存（全局）
    _middleware_cache: Optional[List[Any]] = None

    # 工具缓存：权限组合 -> 工具列表
    # key 是 frozenset(permissions) 的哈希值
    _tools_cache: Dict[int, List[Any]] = {}

    # 工具名称缓存：权限组合 -> 工具名称集合
    _tool_names_cache: Dict[int, Set[str]] = {}

    # 缓存统计
    _cache_hits = 0
    _cache_misses = 0

    # ========== Subagent 相关 ==========

    @classmethod
    def get_subagents(cls) -> List[Dict[str, Any]]:
        """
        获取缓存的 Subagent 列表

        Returns:
            Subagent 配置列表
        """
        if cls._subagents_cache is None:
            logger.info("📦 加载 Subagent 列表（首次）")

            cls._subagents_cache = get_all_subagents()
            logger.info(f"✅ 已缓存 {len(cls._subagents_cache)} 个 Subagent")
        else:
            logger.debug(f"📦 使用缓存的 Subagent 列表（{len(cls._subagents_cache)} 个）")

        return cls._subagents_cache

    @classmethod
    def invalidate_subagents(cls) -> None:
        """清除 Subagent 缓存"""
        cls._subagents_cache = None
        logger.info("🗑️ 已清除 Subagent 缓存")

    # ========== 中间件相关 ==========

    @classmethod
    def get_middleware(cls) -> List[Any]:
        """
        获取缓存的中间件列表

        Returns:
            中间件实例列表
        """
        if cls._middleware_cache is None:
            logger.info("📦 加载中间件列表（首次）")

            cls._middleware_cache = [
                ErrorFilteringMiddleware(),
                LoggingMiddleware(),
            ]
            logger.info(f"✅ 已缓存 {len(cls._middleware_cache)} 个中间件")
        else:
            logger.debug(f"📦 使用缓存的中间件列表（{len(cls._middleware_cache)} 个）")

        return cls._middleware_cache

    @classmethod
    def invalidate_middleware(cls) -> None:
        """清除中间件缓存"""
        cls._middleware_cache = None
        logger.info("🗑️ 已清除中间件缓存")


    @classmethod
    def get_tools(
        cls,
        permissions: Optional[Set[str]] = None,
        user_id: Optional[int] = None,
        db = None,
    ) -> List[Any]:
        """
        获取工具列表（带缓存）

        根据权限过滤工具，相同权限组合使用缓存。

        Args:
            permissions: 用户权限集合
            user_id: 用户 ID（用于动态权限）
            db: 数据库会话（用于动态权限）

        Returns:
            过滤后的工具列表
        """
        # 计算缓存 key
        cache_key = cls._compute_tools_cache_key(permissions, user_id)

        if cache_key in cls._tools_cache:
            cls._cache_hits += 1
            tool_count = len(cls._tools_cache[cache_key])
            logger.info(f"📦 使用缓存的工具列表（{tool_count} 个工具，权限组合: {cache_key}）")
            return cls._tools_cache[cache_key]

        cls._cache_misses += 1
        logger.info(f"📦 加载工具列表（首次，权限: {permissions or '全部'}）")

        # 从 ToolRegistry 获取工具

        registry = get_tool_registry()

        if user_id is not None and db is not None:
            # 动态权限
            tools = registry.get_langchain_tools(user_id=user_id, db=db)
        elif permissions is not None:
            # 静态权限
            tools = registry.get_langchain_tools(permissions=permissions)
        else:
            # 无权限过滤
            tools = registry.get_langchain_tools()

        # 存入缓存
        cls._tools_cache[cache_key] = tools
        cls._tool_names_cache[cache_key] = {t.name for t in tools}

        logger.info(f"✅ 已缓存 {len(tools)} 个工具（权限组合: {cache_key}）")

        return tools

    @classmethod
    def get_tool_names(
        cls,
        permissions: Optional[Set[str]] = None,
        user_id: Optional[int] = None,
    ) -> Set[str]:
        """
        获取工具名称集合（带缓存）

        Args:
            permissions: 用户权限集合
            user_id: 用户 ID

        Returns:
            工具名称集合
        """
        cache_key = cls._compute_tools_cache_key(permissions, user_id)

        if cache_key in cls._tool_names_cache:
            return cls._tool_names_cache[cache_key]

        # 如果没有名称缓存，加载工具
        tools = cls.get_tools(permissions, user_id)
        return cls._tool_names_cache.get(cache_key, set())

    @classmethod
    def invalidate_tools(cls, permissions: Optional[Set[str]] = None) -> None:
        """
        清除工具缓存

        Args:
            permissions: 如果指定，只清除该权限组合的缓存；否则清除所有
        """
        if permissions is not None:
            cache_key = cls._compute_tools_cache_key(permissions)
            if cache_key in cls._tools_cache:
                del cls._tools_cache[cache_key]
                del cls._tool_names_cache[cache_key]
                logger.info(f"🗑️ 已清除工具缓存（权限组合: {cache_key}）")
        else:
            cls._tools_cache.clear()
            cls._tool_names_cache.clear()
            logger.info("🗑️ 已清除所有工具缓存")

    @classmethod
    def invalidate_all(cls) -> None:
        """清除所有缓存"""
        cls.invalidate_subagents()
        cls.invalidate_middleware()
        cls.invalidate_tools()
        logger.info("🗑️ 已清除所有组件缓存")

    # ========== 统计相关 ==========

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            "subagents_cached": cls._subagents_cache is not None,
            "middleware_cached": cls._middleware_cache is not None,
            "tools_cache_count": len(cls._tools_cache),
            "cache_hits": cls._cache_hits,
            "cache_misses": cls._cache_misses,
            "hit_rate": (
                cls._cache_hits / (cls._cache_hits + cls._cache_misses) * 100
                if (cls._cache_hits + cls._cache_misses) > 0
                else 0
            ),
        }

    @classmethod
    def reset_stats(cls) -> None:
        """重置统计信息"""
        cls._cache_hits = 0
        cls._cache_misses = 0

    # ========== 私有方法 ==========

    @classmethod
    def _compute_tools_cache_key(
        cls,
        permissions: Optional[Set[str]] = None,
        user_id: Optional[int] = None,
    ) -> int:
        """
        计算工具缓存的 key

        Args:
            permissions: 权限集合
            user_id: 用户 ID

        Returns:
            缓存 key（哈希值）
        """
        if permissions is not None:
            # 使用权限集合的冻结集合哈希
            return hash(frozenset(permissions))
        elif user_id is not None:
            # 使用用户 ID（动态权限场景）
            return hash(f"user_{user_id}")
        else:
            # 无权限过滤
            return hash("all_tools")


__all__ = ["ComponentCache"]
