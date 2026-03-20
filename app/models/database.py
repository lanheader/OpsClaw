# app/models/database.py
"""数据库配置和会话管理"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import os

# 从环境变量获取数据库 URL 或使用默认值
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/ops_agent_v2.db")

# 创建 SQLAlchemy 引擎
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
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
