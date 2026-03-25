# app/models/database.py
"""数据库配置和会话管理"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import os
import logging

logger = logging.getLogger(__name__)

# 从环境变量获取数据库 URL 或使用默认值
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/ops_agent_v2.db")

# 创建 SQLAlchemy 引擎
if "sqlite" in DATABASE_URL:
    # SQLite 配置：启用 WAL 模式以减少数据库锁定
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=None,  # SQLite 不需要连接池
        pool_pre_ping=True,  # 检查连接是否有效
        echo=False,
    )

    # 启用 WAL 模式以提升并发性能
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-10000")  # 10MB 缓存
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA mmap_size=268435456")  # 256MB 内存映射
        cursor.close()
else:
    # 其他数据库（PostgreSQL, MySQL 等）
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )

# 创建 session 工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 所有模型的基类
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI 获取数据库 session 的依赖。

    生成：
        数据库 session

    示例：
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """通过创建所有表来初始化数据库"""
    Base.metadata.create_all(bind=engine)
