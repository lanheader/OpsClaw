# app/models/database.py
"""多数据库配置和会话管理

每个功能域使用独立的 SQLite 数据库文件，提升并发性能：
- auth.db - 认证授权域
- chat.db - 聊天会话域
- workflow.db - 工作流域
- knowledge.db - 知识库域
- config.db - 配置域
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from typing import Generator, Dict, Any
import os
import logging

logger = logging.getLogger(__name__)

# 数据库文件目录
DB_DIR = os.getenv("DB_DIR", "./workspace/data")
os.makedirs(DB_DIR, exist_ok=True)

# 功能域数据库配置
DOMAIN_DATABASES = {
    "auth": f"sqlite:///{DB_DIR}/auth.db",
    "chat": f"sqlite:///{DB_DIR}/chat.db",
    "workflow": f"sqlite:///{DB_DIR}/workflow.db",
    "knowledge": f"sqlite:///{DB_DIR}/knowledge.db",
    "config": f"sqlite:///{DB_DIR}/config.db",
}


def create_sqlite_engine(database_url: str):
    """创建 SQLite 引擎并启用 WAL 模式"""
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        poolclass=None,  # SQLite 不需要连接池
        pool_pre_ping=True,
        echo=False,
    )

    # 启用 WAL 模式以提升并发性能
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-10000")  # 10MB 缓存
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA mmap_size=268435456")  # 256MB 内存映射
        cursor.close()

    return engine


# 为每个功能域创建独立的引擎和 Base
engines: Dict[str, Any] = {}
bases: Dict[str, Any] = {}
session_makers: Dict[str, Any] = {}

for domain, db_url in DOMAIN_DATABASES.items():
    engines[domain] = create_sqlite_engine(db_url)
    bases[domain] = declarative_base()
    session_makers[domain] = sessionmaker(
        autocommit=False, autoflush=False, bind=engines[domain]
    )
    logger.info(f"✅ 初始化 {domain} 数据库: {db_url}")


# 向后兼容：默认使用 auth 数据库
Base = bases["auth"]
engine = engines["auth"]
SessionLocal = session_makers["auth"]


def get_db(domain: str = "auth") -> Generator[Session, None, None]:
    """
    获取指定功能域的数据库 session。

    Args:
        domain: 功能域名称 (auth/chat/workflow/knowledge/config)

    生成：
        数据库 session

    示例：
        @app.get("/users")
        def get_users(db: Session = Depends(lambda: get_db("auth"))):
            return db.query(User).all()
    """
    SessionMaker = session_makers.get(domain, SessionLocal)
    db = SessionMaker()
    try:
        yield db
    finally:
        db.close()


def get_auth_db() -> Generator[Session, None, None]:
    """获取认证域数据库 session"""
    yield from get_db("auth")


def get_chat_db() -> Generator[Session, None, None]:
    """获取聊天域数据库 session"""
    yield from get_db("chat")


def get_workflow_db() -> Generator[Session, None, None]:
    """获取工作流域数据库 session"""
    yield from get_db("workflow")


def get_knowledge_db() -> Generator[Session, None, None]:
    """获取知识库域数据库 session"""
    yield from get_db("knowledge")


def get_config_db() -> Generator[Session, None, None]:
    """获取配置域数据库 session"""
    yield from get_db("config")


def init_db():  # type: ignore[no-untyped-def]
    """初始化所有功能域的数据库表"""
    for domain, base in bases.items():
        engine = engines[domain]
        logger.info(f"🔧 初始化 {domain} 数据库表...")
        base.metadata.create_all(bind=engine)
        table_count = len(base.metadata.tables)
        logger.info(f"✅ {domain} 数据库: {table_count} 个表创建完成")


def init_domain_db(domain: str):  # type: ignore[no-untyped-def]
    """初始化指定功能域的数据库表"""
    if domain not in bases:
        raise ValueError(f"未知的功能域: {domain}")

    base = bases[domain]
    engine = engines[domain]
    logger.info(f"🔧 初始化 {domain} 数据库表...")
    base.metadata.create_all(bind=engine)
    table_count = len(base.metadata.tables)
    logger.info(f"✅ {domain} 数据库: {table_count} 个表创建完成")
