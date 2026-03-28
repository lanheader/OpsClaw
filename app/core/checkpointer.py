# app/core/checkpointer.py
"""
LangGraph Checkpointer 管理器

提供统一的 checkpointer 接口，支持多种后端实现（SQLite、PostgreSQL、Redis 等）。
"""

import os
import aiosqlite
from abc import ABC, abstractmethod
from typing import Optional
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.core.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CheckpointerFactory(ABC):
    """
    Checkpointer 工厂抽象基类

    定义了创建 checkpointer 的统一接口，方便以后扩展不同的存储后端。
    """

    @abstractmethod
    async def create_checkpointer(self) -> BaseCheckpointSaver:
        """
        创建 checkpointer 实例

        Returns:
            BaseCheckpointSaver 实例
        """
        pass


class SQLiteCheckpointerFactory(CheckpointerFactory):
    """
    SQLite Checkpointer 工厂

    使用 LangGraph 官方的 AsyncSqliteSaver，自动在同一个 SQLite 文件中
    创建 checkpoints 和 checkpoint_writes 表。

    特点：
    - 与业务表（chat_sessions、chat_messages）共享同一个数据库文件
    - 通过 thread_id = session_id 关联
    - 重启后状态不丢失
    """

    def __init__(self, db_path: str):
        """
        初始化工厂

        Args:
            db_path: SQLite 数据库文件路径（如 ./data/ops_agent_v2.db）
        """
        self.db_path = db_path
        self._checkpointer: Optional[AsyncSqliteSaver] = None
        self._conn = None
        logger.info(f"SQLiteCheckpointerFactory 初始化: {db_path}")

    async def create_checkpointer(self) -> AsyncSqliteSaver:
        """
        创建并持有 SQLite checkpointer（保持连接常驻）

        AsyncSqliteSaver 需要保持 aiosqlite 连接，不能每次都重新创建。

        Returns:
            已初始化的 AsyncSqliteSaver 实例
        """
        if self._checkpointer is not None:
            return self._checkpointer

        # 确保数据库目录存在
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        logger.info(f"创建 SQLite checkpointer 连接: {self.db_path}")

        # 建立持久连接（进程生命周期内保持）
        self._conn = await aiosqlite.connect(self.db_path)
        self._checkpointer = AsyncSqliteSaver(self._conn)

        # 初始化表结构（自动创建 checkpoints 和 checkpoint_writes 表）
        await self._checkpointer.setup()
        logger.info("✅ SQLite checkpointer 表初始化完成")

        return self._checkpointer


class PostgreSQLCheckpointerFactory(CheckpointerFactory):
    """
    PostgreSQL Checkpointer 工厂（预留，未实现）

    未来如果需要切换到 PostgreSQL，可以在这里实现。
    """

    def __init__(self, db_url: str):
        self.db_url = db_url
        logger.info(f"PostgreSQLCheckpointerFactory 初始化: {db_url}")

    async def create_checkpointer(self) -> BaseCheckpointSaver:
        """创建 PostgreSQL checkpointer"""
        raise NotImplementedError("PostgreSQL checkpointer 尚未实现")


# 全局 checkpointer 实例（单例）
_checkpointer: Optional[BaseCheckpointSaver] = None
_factory: Optional[CheckpointerFactory] = None


def get_checkpointer_factory() -> CheckpointerFactory:
    """
    获取 checkpointer 工厂（根据配置自动选择）

    Returns:
        CheckpointerFactory 实例
    """
    global _factory
    if _factory is not None:
        return _factory

    settings = get_settings()
    db_url = settings.get_checkpoint_db_url()

    if db_url.startswith("sqlite"):
        # 提取 SQLite 文件路径
        db_path = db_url.replace("sqlite:///", "")
        _factory = SQLiteCheckpointerFactory(db_path)
        logger.info("使用 SQLite checkpointer")
    elif db_url.startswith("postgresql"):
        _factory = PostgreSQLCheckpointerFactory(db_url)
        logger.info("使用 PostgreSQL checkpointer")
    else:
        raise ValueError(f"不支持的数据库类型: {db_url}")

    return _factory


async def get_checkpointer() -> BaseCheckpointSaver:
    """
    获取全局 checkpointer 实例（懒加载）

    使用工厂模式创建 checkpointer，支持多种后端。
    通过 thread_id = session_id 与 chat_sessions 表关联。

    Returns:
        BaseCheckpointSaver 实例
    """
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    factory = get_checkpointer_factory()
    _checkpointer = await factory.create_checkpointer()

    logger.info(f"✅ Checkpointer 初始化完成: {type(_checkpointer).__name__}")
    return _checkpointer


async def shutdown_checkpointer() -> None:
    """
    关闭 checkpointer 连接

    在应用关闭时调用，确保数据库连接正确关闭。
    """
    global _checkpointer, _factory

    if _factory is not None and isinstance(_factory, SQLiteCheckpointerFactory):
        if _factory._conn is not None:
            await _factory._conn.close()
            logger.info("✅ SQLite checkpointer 连接已关闭")

    _checkpointer = None
    _factory = None
    logger.info("✅ Checkpointer 已清理")


__all__ = [
    "get_checkpointer",
    "get_checkpointer_factory",
    "shutdown_checkpointer",
    "CheckpointerFactory",
    "SQLiteCheckpointerFactory",
    "PostgreSQLCheckpointerFactory",
]
