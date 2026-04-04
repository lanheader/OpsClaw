"""
SQLite FTS5 记忆存储（无 embedding 依赖）

用于无 embedding 模型的生产环境，基于关键词匹配 + BM25 排序。
"""

import sqlite3
import json
import os
import re
from typing import List, Dict, Optional, Any
from datetime import datetime

from app.utils.logger import get_logger

logger = get_logger(__name__)


class SQLiteMemoryStore:
    """
    基于 SQLite FTS5 的记忆存储

    三张表：
    - incidents_fts / incidents_meta: 故障记忆
    - knowledge_fts / knowledge_meta: 知识库
    - session_summaries: 会话摘要
    """

    def __init__(self, db_path: str = "./workspace/data/memory.db"):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.db_path = db_path
        self._init_tables()
        logger.info(f"✅ SQLite FTS5 记忆存储初始化完成 | {db_path}")

    def _init_tables(self):  # type: ignore[no-untyped-def]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS incidents_fts
                USING fts5(title, content, incident_type, resolution, root_cause,
                           tokenize='unicode61')
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS incidents_meta (
                    rowid INTEGER PRIMARY KEY,
                    id TEXT UNIQUE,
                    created_at TEXT,
                    has_resolution INTEGER DEFAULT 0,
                    has_root_cause INTEGER DEFAULT 0,
                    extra_meta TEXT
                )
            """)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
                USING fts5(title, content, category, tags, source,
                           tokenize='unicode61')
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_meta (
                    rowid INTEGER PRIMARY KEY,
                    id TEXT UNIQUE,
                    created_at TEXT,
                    extra_meta TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_summaries (
                    session_id TEXT PRIMARY KEY,
                    summary TEXT,
                    updated_at TEXT
                )
            """)
            conn.commit()

    @staticmethod
    def _escape_fts_query(query: str) -> str:
        """
        转义 FTS5 特殊字符，将词转为 OR 查询

        FTS5 特殊字符: " * ( ) ^ # : - |
        空查询返回空字符串，调用方需要特殊处理
        """
        if not query or not query.strip():
            return ""

        # 移除 FTS5 特殊运算符字符（保留字母数字和中文）
        # 这些字符在 FTS5 中有特殊含义，可能导致语法错误
        cleaned = re.sub(r'[*()^#:|\-]', ' ', query)

        # 转义双引号
        cleaned = cleaned.replace('"', '""')

        # 把空格/逗号分隔的词转为 OR 查询
        terms = [f'"{t.strip()}"' for t in re.split(r'[\s,;，；]+', cleaned) if t.strip()]

        if not terms:
            return ""

        return " OR ".join(terms)

    # ===== 故障记忆 =====

    def store_incident(
        self, content: str, incident_type: str = "general",
        title: str = None, resolution: str = None,  # type: ignore[assignment]
        root_cause: str = None, metadata: dict = None  # type: ignore[assignment]
    ) -> str:
        doc_id = f"incident_{datetime.now().timestamp()}"
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO incidents_fts (title, content, incident_type, resolution, root_cause) VALUES (?,?,?,?,?)",
                [title or "", content, incident_type, resolution or "", root_cause or ""]
            )
            rowid = cursor.lastrowid
            conn.execute(
                "INSERT OR IGNORE INTO incidents_meta (rowid, id, created_at, has_resolution, has_root_cause, extra_meta) VALUES (?,?,?,?,?,?)",
                [rowid, doc_id, datetime.now().isoformat(),
                 int(bool(resolution)), int(bool(root_cause)),
                 json.dumps(metadata or {})]
            )
            conn.commit()
        logger.debug(f"💾 [FTS5] 存储故障记忆: {doc_id}")
        return doc_id

    def search_incidents(self, query, top_k=5, incident_type=None):
        terms = self._escape_fts_query(query)
        if not terms:
            return []

        with sqlite3.connect(self.db_path) as conn:
            sql = """
                  SELECT f.rowid, f.title, f.content, f.incident_type,
                         f.resolution, f.root_cause, m.created_at,
                         bm25(incidents_fts) as rank
                  FROM incidents_fts f
                           JOIN incidents_meta m ON f.rowid = m.rowid
                  WHERE incidents_fts MATCH ?
                  ORDER BY rank LIMIT ? \
                  """
            rows = conn.execute(sql, [terms, top_k]).fetchall()

            results = []
            for r in rows:
                # rank 是负数，越小越相关
                rank = r[7]  # bm25 rank

                # 转换为相似度：rank 越小 → 分数越高
                # 用 sigmoid 变换：score = 1 / (1 + e^(rank/10))
                # -10 → 0.73, -5 → 0.62, -1 → 0.52, 0 → 0.50, -50 → 0.99
                import math
                score = 1.0 / (1.0 + math.exp(rank / 10.0))

                # 过滤：只返回相似度 > 0.5 的结果
                if score < 0.5:
                    continue

                results.append({
                    "id": f"incident_{r[0]}",
                    "title": r[1],
                    "content": r[2],
                    "incident_type": r[3],
                    "resolution": r[4],
                    "root_cause": r[5],
                    "created_at": r[6],
                    "similarity": round(score, 3),  # ← 用真实分数
                })

            return results

    # ===== 知识库 =====

    def store_knowledge(
        self, title: str, content: str, category: str = "general",
        tags: List[str] = None, source: str = None, metadata: dict = None  # type: ignore[assignment]
    ) -> str:
        doc_id = f"knowledge_{datetime.now().timestamp()}"
        tags_str = ",".join(tags or [])
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO knowledge_fts (title, content, category, tags, source) VALUES (?,?,?,?,?)",
                [title, content, category, tags_str, source or ""]
            )
            rowid = cursor.lastrowid
            conn.execute(
                "INSERT OR IGNORE INTO knowledge_meta (rowid, id, created_at, extra_meta) VALUES (?,?,?,?)",
                [rowid, doc_id, datetime.now().isoformat(), json.dumps(metadata or {})]
            )
            conn.commit()
        logger.debug(f"💾 [FTS5] 存储知识: {doc_id}")
        return doc_id

    def search_knowledge(
        self, query: str, top_k: int = 5, category: str = None  # type: ignore[assignment]
    ) -> List[Dict[str, Any]]:
        terms = self._escape_fts_query(query)

        # 空查询时返回空列表
        if not terms:
            return []

        try:
            with sqlite3.connect(self.db_path) as conn:
                if category:
                    sql = """
                        SELECT f.rowid, f.title, f.content, f.category, f.tags, f.source,
                               m.created_at, bm25(knowledge_fts) as rank
                        FROM knowledge_fts f
                        JOIN knowledge_meta m ON f.rowid = m.rowid
                        WHERE knowledge_fts MATCH ? AND f.category = ?
                        ORDER BY rank LIMIT ?
                    """
                    rows = conn.execute(sql, [terms, category, top_k]).fetchall()
                else:
                    sql = """
                        SELECT f.rowid, f.title, f.content, f.category, f.tags, f.source,
                               m.created_at, bm25(knowledge_fts) as rank
                        FROM knowledge_fts f
                        JOIN knowledge_meta m ON f.rowid = m.rowid
                        WHERE knowledge_fts MATCH ?
                        ORDER BY rank LIMIT ?
                    """
                    rows = conn.execute(sql, [terms, top_k]).fetchall()

                return [
                    {
                        "id": f"knowledge_{r[0]}",
                        "title": r[1], "content": r[2],
                        "category": r[3],
                        "tags": r[4].split(",") if r[4] else [],
                        "source": r[5], "created_at": r[6],
                        "similarity": 1.0,
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.warning(f"⚠️ FTS5 知识搜索失败: {e}")
            return []

    # ===== 会话摘要 =====

    def store_summary(self, session_id: str, summary: str):  # type: ignore[no-untyped-def]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO session_summaries (session_id, summary, updated_at)
                VALUES (?, ?, ?)
            """, [session_id, summary, datetime.now().isoformat()])
            conn.commit()
        logger.debug(f"💾 [FTS5] 存储会话摘要: {session_id}")

    def get_summary(self, session_id: str) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT summary FROM session_summaries WHERE session_id = ?",
                [session_id]
            ).fetchone()
            return row[0] if row else None

    # ===== 会话记忆 =====

    def search_session_history(
        self, session_id: str, query: str = None, top_k: int = 10  # type: ignore[assignment]
    ) -> List[Dict[str, Any]]:
        # keyword 模式下会话记忆不做语义搜索，直接返回空
        # 会话上下文由 checkpointer 的 messages 管理
        return []

    # ===== 统计 =====

    def get_stats(self) -> Dict[str, int]:
        with sqlite3.connect(self.db_path) as conn:
            incidents = conn.execute("SELECT COUNT(*) FROM incidents_fts").fetchone()[0]
            knowledge = conn.execute("SELECT COUNT(*) FROM knowledge_fts").fetchone()[0]
            summaries = conn.execute("SELECT COUNT(*) FROM session_summaries").fetchone()[0]
        return {
            "incident_memories": incidents,
            "knowledge_memories": knowledge,
            "session_summaries": summaries,
        }

    # ===== 清理 =====

    def clear_session(self, session_id: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM session_summaries WHERE session_id = ?", [session_id])
                conn.commit()
            return True
        except Exception as e:
            logger.warning(f"⚠️ 清除会话摘要失败: {e}")
            return False


__all__ = ["SQLiteMemoryStore"]
