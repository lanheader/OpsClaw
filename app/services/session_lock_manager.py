"""
会话锁管理器

保证同一会话的请求串行处理，避免多渠道并发时的状态冲突。

使用场景：
- Web 和飞书同时向同一会话发送消息
- 同一用户在多个设备上同时操作

工作原理：
- 每个 session_id 对应一个 asyncio.Lock
- 同一会话的请求必须获取锁后才能执行
- 不同会话的请求可以并行执行
- 使用 LRU 淘汰策略，自动清理空闲锁，防止内存泄漏
"""

import asyncio
import time
from collections import OrderedDict
from typing import Dict, Optional, Tuple
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SessionLockManager:
    """
    会话锁管理器 - 保证同一会话的请求串行处理

    使用方式：
        async with await SessionLockManager.acquire(session_id):
            # 执行会话相关操作
            ...

    特点：
    - 使用 OrderedDict 实现 LRU 淘汰
    - 最大锁数量限制（默认 1000）
    - 空闲超时自动清理（默认 30 分钟）
    - 防止长期运行的内存泄漏
    """

    # 会话锁字典：session_id -> (asyncio.Lock, last_access_time)
    _session_locks: OrderedDict[str, Tuple[asyncio.Lock, float]] = OrderedDict()

    # 保护 _session_locks 字典的锁
    _manager_lock = asyncio.Lock()

    # 锁超时时间（秒）
    LOCK_TIMEOUT = 300  # 5 分钟

    # 最大锁数量（LRU 淘汰阈值）
    MAX_LOCKS = 1000

    # 空闲锁超时时间（秒），超过此时间未使用的锁会被清理
    IDLE_TIMEOUT = 1800  # 30 分钟

    @classmethod
    async def acquire(cls, session_id: str) -> asyncio.Lock:
        """
        获取会话锁

        Args:
            session_id: 会话 ID

        Returns:
            该会话对应的锁对象
        """
        async with cls._manager_lock:
            # 清理空闲超时的锁
            await cls._cleanup_idle_locks()

            if session_id not in cls._session_locks:
                # LRU 淘汰：如果超过最大数量，移除最旧的
                while len(cls._session_locks) >= cls.MAX_LOCKS:
                    oldest_id, _ = cls._session_locks.popitem(last=False)
                    logger.debug(f"🔒 LRU 淘汰会话锁: {oldest_id}")

                cls._session_locks[session_id] = (asyncio.Lock(), time.monotonic())
                logger.debug(f"🔒 创建会话锁: {session_id}")
            else:
                # 更新访问时间并移到末尾（LRU）
                lock, _ = cls._session_locks.pop(session_id)
                cls._session_locks[session_id] = (lock, time.monotonic())

            return cls._session_locks[session_id][0]

    @classmethod
    async def _cleanup_idle_locks(cls) -> None:
        """清理空闲超时的锁（在持有 _manager_lock 时调用）"""
        now = time.monotonic()
        expired_keys = [
            sid for sid, (_, last_access) in cls._session_locks.items()
            if now - last_access > cls.IDLE_TIMEOUT and not _.locked()
        ]
        for sid in expired_keys:
            del cls._session_locks[sid]
            logger.debug(f"🔓 清理空闲会话锁: {sid}")
        if expired_keys:
            logger.info(f"🧹 清理了 {len(expired_keys)} 个空闲会话锁")

    @classmethod
    async def get_lock(cls, session_id: str) -> asyncio.Lock:
        """获取会话锁（acquire 的别名）"""
        return await cls.acquire(session_id)

    @classmethod
    def has_lock(cls, session_id: str) -> bool:
        """检查会话是否有锁"""
        return session_id in cls._session_locks

    @classmethod
    def remove_lock(cls, session_id: str) -> None:
        """
        移除会话锁

        注意：只在会话结束时调用，避免内存泄漏
        """
        if session_id in cls._session_locks:
            del cls._session_locks[session_id]
            logger.debug(f"🔓 移除会话锁: {session_id}")

    @classmethod
    def get_active_sessions(cls) -> int:
        """获取当前活跃的会话锁数量"""
        return len(cls._session_locks)

    @classmethod
    def clear_all(cls) -> None:
        """清除所有会话锁（仅用于测试或重置）"""
        cls._session_locks.clear()
        logger.warning("⚠️ 已清除所有会话锁")


class SessionLockContext:
    """
    会话锁上下文管理器

    使用方式：
        async with SessionLockContext(session_id) as lock:
            # 持有锁，执行操作
            ...
        # 自动释放锁
    """

    def __init__(self, session_id: str, timeout: Optional[float] = None):
        self.session_id = session_id
        self.timeout = timeout or SessionLockManager.LOCK_TIMEOUT
        self._lock: Optional[asyncio.Lock] = None
        self._acquired = False

    async def __aenter__(self) -> asyncio.Lock:
        self._lock = await SessionLockManager.acquire(self.session_id)

        logger.debug(f"🔒 等待获取会话锁: {self.session_id}")

        # 带超时的锁获取
        try:
            await asyncio.wait_for(
                self._lock.acquire(),
                timeout=self.timeout
            )
            self._acquired = True
            logger.info(f"✅ 获取会话锁成功: {self.session_id}")
            return self._lock
        except asyncio.TimeoutError:
            logger.error(f"⏰ 获取会话锁超时: {self.session_id} ({self.timeout}s)")
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._acquired and self._lock:
            self._lock.release()
            logger.info(f"🔓 释放会话锁: {self.session_id}")
        return False  # 不抑制异常


async def with_session_lock(session_id: str, coro, timeout: Optional[float] = None):
    """
    在会话锁保护下执行协程

    Args:
        session_id: 会话 ID
        coro: 要执行的协程
        timeout: 锁超时时间

    Returns:
        协程的返回值

    Usage:
        result = await with_session_lock(session_id, some_async_function())
    """
    async with SessionLockContext(session_id, timeout):
        return await coro


__all__ = [
    "SessionLockManager",
    "SessionLockContext",
    "with_session_lock",
]
