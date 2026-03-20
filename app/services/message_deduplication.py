"""消息去重服务 - 防止重复处理同一条消息"""

from datetime import datetime, timedelta
from typing import Optional, Set
import threading
from app.utils.logger import get_logger

logger = get_logger(__name__)


class MessageDeduplicationService:
    """
    消息去重服务

    使用内存缓存记录最近处理过的消息ID，防止重复处理。
    自动清理过期的消息ID（默认保留1小时）。
    """

    def __init__(self, ttl_minutes: int = 60):
        """
        初始化去重服务

        Args:
            ttl_minutes: 消息ID在缓存中的存活时间（分钟）
        """
        self._processed_messages: dict[str, datetime] = {}
        self._lock = threading.Lock()
        self._ttl_minutes = ttl_minutes
        logger.info(f"✅ 消息去重服务已初始化，TTL={ttl_minutes}分钟")

    def is_duplicate(self, message_id: str) -> bool:
        """
        检查消息是否已处理过

        Args:
            message_id: 消息ID（如飞书的 message_id）

        Returns:
            True 表示重复消息，False 表示新消息
        """
        if not message_id:
            logger.warning("⚠️ 消息ID为空，跳过去重检查")
            return False

        with self._lock:
            # 先清理过期的消息ID
            self._cleanup_expired()

            # 检查是否已处理
            if message_id in self._processed_messages:
                logger.warning(f"⚠️ 检测到重复消息: {message_id}")
                return True

            # 记录新消息
            self._processed_messages[message_id] = datetime.now()
            logger.info(f"✅ 新消息已记录: {message_id}")
            return False

    def mark_as_processed(self, message_id: str) -> None:
        """
        标记消息为已处理

        Args:
            message_id: 消息ID
        """
        if not message_id:
            return

        with self._lock:
            self._processed_messages[message_id] = datetime.now()
            logger.info(f"✅ 消息已标记为已处理: {message_id}")

    def _cleanup_expired(self) -> None:
        """清理过期的消息ID（内部方法，需要持有锁）"""
        now = datetime.now()
        expired_threshold = now - timedelta(minutes=self._ttl_minutes)

        expired_ids = [
            msg_id
            for msg_id, timestamp in self._processed_messages.items()
            if timestamp < expired_threshold
        ]

        for msg_id in expired_ids:
            del self._processed_messages[msg_id]

        if expired_ids:
            logger.info(f"🧹 清理了 {len(expired_ids)} 个过期消息ID")

    def get_stats(self) -> dict:
        """
        获取去重服务统计信息

        Returns:
            统计信息字典
        """
        with self._lock:
            return {
                "total_cached": len(self._processed_messages),
                "ttl_minutes": self._ttl_minutes,
            }

    def clear(self) -> None:
        """清空所有缓存的消息ID"""
        with self._lock:
            count = len(self._processed_messages)
            self._processed_messages.clear()
            logger.info(f"🧹 已清空所有缓存的消息ID（共 {count} 个）")


# 全局单例
_deduplication_service: Optional[MessageDeduplicationService] = None


def get_deduplication_service() -> MessageDeduplicationService:
    """获取全局消息去重服务单例"""
    global _deduplication_service
    if _deduplication_service is None:
        _deduplication_service = MessageDeduplicationService(ttl_minutes=60)
    return _deduplication_service
