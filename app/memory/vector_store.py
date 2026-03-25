"""
向量存储模块 - 基于 SQLite + NumPy 实现向量检索

支持：
- 故障记忆向量存储
- 知识库向量存储
- 会话记忆向量存储
- 余弦相似度搜索
"""

import sqlite3
import json
import numpy as np
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from pathlib import Path

from app.utils.logger import get_logger
from app.utils.vector_helpers import cosine_similarity

logger = get_logger(__name__)


class SQLiteVectorStore:
    """基于 SQLite 的向量存储"""

    def __init__(self, db_path: str = "./data/ops_agent_v2.db"):
        self.db_path = db_path
        self._init_db()

    def _get_db(self):
        """获取数据库连接"""
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """初始化向量表"""
        with self._get_db() as db:
            db.executescript("""
                -- 故障记忆表
                CREATE TABLE IF NOT EXISTS incident_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id TEXT,
                    incident_type TEXT,
                    title TEXT,
                    content TEXT NOT NULL,
                    embedding BLOB,
                    resolution TEXT,
                    root_cause TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP,
                    access_count INTEGER DEFAULT 0
                );

                -- 知识库表
                CREATE TABLE IF NOT EXISTS knowledge_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding BLOB,
                    category TEXT,
                    tags TEXT,
                    source TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- 会话记忆表
                CREATE TABLE IF NOT EXISTS session_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding BLOB,
                    importance REAL DEFAULT 0.5,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- 索引
                CREATE INDEX IF NOT EXISTS idx_incident_type
                    ON incident_memories(incident_type);
                CREATE INDEX IF NOT EXISTS idx_knowledge_category
                    ON knowledge_memories(category);
                CREATE INDEX IF NOT EXISTS idx_session_id
                    ON session_memories(session_id);
                CREATE INDEX IF NOT EXISTS idx_incident_created
                    ON incident_memories(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_knowledge_created
                    ON knowledge_memories(created_at DESC);
            """)
            db.commit()
            logger.info("✅ 向量存储表初始化完成")

    async def store_incident(
        self,
        content: str,
        embedding: List[float],
        incident_type: str = "alert",
        title: str = None,
        resolution: str = None,
        root_cause: str = None,
        metadata: dict = None,
        incident_id: str = None
    ) -> int:
        """存储故障记忆"""
        with self._get_db() as db:
            cursor = db.execute("""
                INSERT INTO incident_memories
                (incident_id, content, embedding, incident_type, title, resolution, root_cause, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                incident_id,
                content,
                json.dumps(embedding),
                incident_type,
                title,
                resolution,
                root_cause,
                json.dumps(metadata or {}, ensure_ascii=False)
            ))
            db.commit()
            memory_id = cursor.lastrowid
            logger.debug(f"存储故障记忆: {memory_id} - {title or incident_type}")
            return memory_id

    async def store_knowledge(
        self,
        title: str,
        content: str,
        embedding: List[float],
        category: str = "general",
        tags: List[str] = None,
        source: str = None,
        metadata: dict = None
    ) -> int:
        """存储知识"""
        with self._get_db() as db:
            cursor = db.execute("""
                INSERT INTO knowledge_memories
                (title, content, embedding, category, tags, source, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                title,
                content,
                json.dumps(embedding),
                category,
                json.dumps(tags or [], ensure_ascii=False),
                source,
                json.dumps(metadata or {}, ensure_ascii=False)
            ))
            db.commit()
            memory_id = cursor.lastrowid
            logger.debug(f"存储知识: {memory_id} - {title}")
            return memory_id

    async def store_session_message(
        self,
        session_id: str,
        role: str,
        content: str,
        embedding: List[float],
        importance: float = 0.5
    ) -> int:
        """存储会话消息"""
        with self._get_db() as db:
            cursor = db.execute("""
                INSERT INTO session_memories
                (session_id, role, content, embedding, importance)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, role, content, json.dumps(embedding), importance))
            db.commit()
            return cursor.lastrowid

    async def search_similar(
        self,
        query_embedding: List[float],
        table: str = "incident_memories",
        top_k: int = 5,
        threshold: float = 0.7,
        filters: dict = None
    ) -> List[Dict]:
        """相似度搜索（余弦相似度）"""

        # 构建查询
        if table == "incident_memories":
            base_query = """
                SELECT id, incident_id, title, content, resolution, root_cause,
                       metadata, embedding, incident_type, created_at
                FROM incident_memories
            """
        elif table == "knowledge_memories":
            base_query = """
                SELECT id, title, content, category, tags,
                       metadata, embedding, source, created_at
                FROM knowledge_memories
            """
        elif table == "session_memories":
            base_query = """
                SELECT id, session_id, role, content, importance, embedding, created_at
                FROM session_memories
            """
        else:
            logger.warning(f"未知的表: {table}")
            return []

        # 添加过滤条件
        conditions = []
        params = []
        if filters:
            if "incident_type" in filters:
                conditions.append("incident_type = ?")
                params.append(filters["incident_type"])
            if "category" in filters:
                conditions.append("category = ?")
                params.append(filters["category"])
            if "session_id" in filters:
                conditions.append("session_id = ?")
                params.append(filters["session_id"])

        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)

        # 限制搜索范围以提高性能
        base_query += " ORDER BY created_at DESC LIMIT 1000"

        try:
            with self._get_db() as db:
                cursor = db.execute(base_query, params)
                rows = cursor.fetchall()
        except Exception as e:
            logger.error(f"查询向量存储失败: {e}")
            return []

        # 计算相似度
        query_vec = np.array(query_embedding, dtype=np.float32)
        results = []

        for row in rows:
            try:
                # 根据表结构解析
                if table == "incident_memories":
                    id, incident_id, title, content, resolution, root_cause, metadata, embedding_str, incident_type, created_at = row
                    stored_vec = np.array(json.loads(embedding_str), dtype=np.float32)

                    # 计算余弦相似度
                    similarity = cosine_similarity(query_vec, stored_vec)

                    if similarity >= threshold:
                        results.append({
                            "id": id,
                            "incident_id": incident_id,
                            "title": title,
                            "content": content,
                            "resolution": resolution,
                            "root_cause": root_cause,
                            "metadata": json.loads(metadata or "{}"),
                            "incident_type": incident_type,
                            "similarity": similarity,
                            "created_at": created_at
                        })

                elif table == "knowledge_memories":
                    id, title, content, category, tags, metadata, embedding_str, source, created_at = row
                    stored_vec = np.array(json.loads(embedding_str), dtype=np.float32)

                    similarity = cosine_similarity(query_vec, stored_vec)

                    if similarity >= threshold:
                        results.append({
                            "id": id,
                            "title": title,
                            "content": content,
                            "category": category,
                            "tags": json.loads(tags or "[]"),
                            "metadata": json.loads(metadata or "{}"),
                            "source": source,
                            "similarity": similarity,
                            "created_at": created_at
                        })

                elif table == "session_memories":
                    id, session_id, role, content, importance, embedding_str, created_at = row
                    stored_vec = np.array(json.loads(embedding_str), dtype=np.float32)

                    similarity = cosine_similarity(query_vec, stored_vec)

                    if similarity >= threshold:
                        results.append({
                            "id": id,
                            "session_id": session_id,
                            "role": role,
                            "content": content,
                            "importance": importance,
                            "similarity": similarity,
                            "created_at": created_at
                        })

            except Exception as e:
                logger.warning(f"解析向量失败: {e}")
                continue

        # 按相似度排序
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    async def get_recent_incidents(
        self,
        days: int = 7,
        limit: int = 50,
        incident_type: str = None
    ) -> List[Dict]:
        """获取最近的故障"""
        with self._get_db() as db:
            if incident_type:
                cursor = db.execute("""
                    SELECT id, incident_id, incident_type, title, content,
                           resolution, root_cause, created_at
                    FROM incident_memories
                    WHERE created_at >= datetime('now', ?)
                      AND incident_type = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (f'-{days} days', incident_type, limit))
            else:
                cursor = db.execute("""
                    SELECT id, incident_id, incident_type, title, content,
                           resolution, root_cause, created_at
                    FROM incident_memories
                    WHERE created_at >= datetime('now', ?)
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (f'-{days} days', limit))

            return [
                {
                    "id": row[0],
                    "incident_id": row[1],
                    "type": row[2],
                    "title": row[3],
                    "content": row[4],
                    "resolution": row[5],
                    "root_cause": row[6],
                    "created_at": row[7]
                }
                for row in cursor.fetchall()
            ]

    async def update_access(self, memory_id: int, table: str = "incident_memories"):
        """更新访问记录"""
        with self._get_db() as db:
            db.execute(f"""
                UPDATE {table}
                SET last_accessed = CURRENT_TIMESTAMP,
                    access_count = access_count + 1
                WHERE id = ?
            """, (memory_id,))
            db.commit()

    async def get_memory_stats(self) -> Dict[str, int]:
        """获取记忆统计"""
        with self._get_db() as db:
            incident_count = db.execute("SELECT COUNT(*) FROM incident_memories").fetchone()[0]
            knowledge_count = db.execute("SELECT COUNT(*) FROM knowledge_memories").fetchone()[0]
            session_count = db.execute("SELECT COUNT(*) FROM session_memories").fetchone()[0]

            return {
                "incident_memories": incident_count,
                "knowledge_memories": knowledge_count,
                "session_memories": session_count
            }


# 全局单例
_vector_store_instance: Optional[SQLiteVectorStore] = None


def get_vector_store() -> SQLiteVectorStore:
    """获取向量存储单例"""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = SQLiteVectorStore()
    return _vector_store_instance


__all__ = [
    "SQLiteVectorStore",
    "get_vector_store",
]
