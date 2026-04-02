#!/usr/bin/env python3
"""清理所有会话（包括 Web 和飞书会话）"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.chat_session import ChatSession
from app.models.chat_message import ChatMessage


def clean_all_sessions():
    """清理所有会话"""
    db = next(get_db())

    print("🔧 开始清理所有会话...")

    # 查询所有会话
    all_sessions = db.query(ChatSession).all()

    print(f"找到 {len(all_sessions)} 个会话")

    # 按来源统计
    web_count = sum(1 for s in all_sessions if s.source == "web")
    feishu_count = sum(1 for s in all_sessions if s.source == "feishu")
    print(f"  - Web 会话: {web_count} 个")
    print(f"  - 飞书会话: {feishu_count} 个")

    # 删除每个会话及其消息
    deleted_sessions = 0
    deleted_messages = 0

    for session in all_sessions:
        # 删除会话的所有消息
        messages_count = (
            db.query(ChatMessage).filter(ChatMessage.session_id == session.session_id).delete()
        )
        deleted_messages += messages_count

        # 删除会话
        db.delete(session)
        deleted_sessions += 1

        source_label = "飞书" if session.source == "feishu" else "Web"
        print(f"  ✓ 删除 {source_label} 会话: {session.session_id} ({messages_count} 条消息)")

    db.commit()

    print(f"\n✅ 清理完成")
    print(f"   删除会话: {deleted_sessions} 个")
    print(f"   删除消息: {deleted_messages} 条")


if __name__ == "__main__":
    clean_all_sessions()
