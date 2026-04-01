"""对话历史查询工具集

用于查询用户的聊天历史记录，支持回答"我之前问过什么"这类问题。
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from app.models.chat_session import ChatSession
from app.models.chat_message import ChatMessage, MessageRole
from app.models.database import SessionLocal
from app.tools.base import (
    BaseOpTool,
    ToolCategory,
    OperationType,
    RiskLevel,
    register_tool,
    tool_success_response,
    tool_error_response,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


# 工具分类：新增 chat 类别
class ChatToolCategory(str):
    """对话工具分类"""
    CHAT = "chat"


@register_tool(
    group="chat.history",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=[],  # 无需权限，所有用户都可以查询自己的历史
    description="查询当前会话之前的对话历史，回答'我之前问过什么'等问题",
    examples=[
        "我之前问过什么问题？",
        "我们刚才讨论了什么？",
        "查询历史对话",
    ],
    enabled=True,
    expose_to_agent=True,
)
class GetConversationHistoryTool(BaseOpTool):
    """查询对话历史工具"""

    def __init__(self, db=None):
        self.db = db

    async def execute(
        self,
        session_id: str,
        limit: int = 10,
        include_system: bool = False,
    ) -> Dict[str, Any]:
        """
        查询指定会话的历史消息

        Args:
            session_id: 会话 ID
            limit: 返回的消息数量限制（默认 10 条）
            include_system: 是否包含系统消息（默认不包含）

        Returns:
            {
                "success": True,
                "data": {
                    "session_id": str,
                    "total_messages": int,
                    "messages": [
                        {
                            "role": "user" | "assistant",
                            "content": str,
                            "created_at": str
                        }
                    ]
                }
            }
        """
        try:
            db = SessionLocal()

            # 构建查询
            query = db.query(ChatMessage).filter(
                ChatMessage.session_id == session_id
            )

            # 过滤系统消息（如果不需要）
            if not include_system:
                query = query.filter(ChatMessage.role != MessageRole.SYSTEM)

            # 按时间倒序，取前 N 条
            query = query.order_by(ChatMessage.created_at.desc()).limit(limit)

            messages = query.all()

            # 转换为可读格式（反转顺序，使最新的在最后）
            history = []
            for msg in reversed(messages):
                history.append({
                    "role": msg.role.value,
                    "content": msg.content,
                    "created_at": msg.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                })

            db.close()

            # 构建摘要
            user_questions = [msg["content"] for msg in history if msg["role"] == "user"]

            return tool_success_response(
                data={
                    "session_id": session_id,
                    "total_messages": len(history),
                    "messages": history,
                    "summary": {
                        "user_questions_count": len(user_questions),
                        "user_questions": user_questions,
                        "time_range": f"{history[0]['created_at']} - {history[-1]['created_at']}" if history else "无记录",
                    }
                },
                tool_name="get_conversation_history",
            )

        except Exception as e:
            logger.error(f"查询对话历史失败: {e}")
            return tool_error_response(
                error=e,
                tool_name="get_conversation_history",
                context={"session_id": session_id},
                suggestion="请检查会话 ID 是否正确",
            )


@register_tool(
    group="chat.history",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=[],
    description="查询用户的所有历史会话列表",
    examples=[
        "我有过哪些会话？",
        "列出我的历史对话",
    ],
    enabled=True,
    expose_to_agent=True,
)
class ListUserSessionsTool(BaseOpTool):
    """列出用户的所有会话工具"""

    def __init__(self, db=None):
        self.db = db

    async def execute(
        self,
        user_id: Optional[int] = None,
        sender_id: Optional[str] = None,  # 飞书 sender_id
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        查询用户的所有会话

        Args:
            user_id: 用户 ID（Web 用户）
            sender_id: 飞书用户 ID
            limit: 返回的会话数量限制

        Returns:
            {
                "success": True,
                "data": {
                    "total_sessions": int,
                    "sessions": [
                        {
                            "session_id": str,
                            "created_at": str,
                            "message_count": int,
                            "last_activity": str
                        }
                    ]
                }
            }
        """
        try:
            db = SessionLocal()

            # 构建查询
            query = db.query(ChatSession)

            if user_id:
                query = query.filter(ChatSession.user_id == user_id)
            elif sender_id:
                query = query.filter(ChatSession.external_user_id == sender_id)
            else:
                # 如果都没有提供，返回最近的所有会话
                pass

            # 按创建时间倒序
            query = query.order_by(ChatSession.created_at.desc()).limit(limit)

            sessions = query.all()

            # 转换为可读格式
            result = []
            for session in sessions:
                # 获取每个会话的消息数量
                msg_count = db.query(ChatMessage).filter(
                    ChatMessage.session_id == session.session_id
                ).count()

                result.append({
                    "session_id": session.session_id,
                    "created_at": session.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "source": session.source,
                    "message_count": msg_count,
                    "is_active": session.is_active,
                    "state": session.state,
                })

            db.close()

            return tool_success_response(
                data={
                    "total_sessions": len(result),
                    "sessions": result,
                },
                tool_name="list_user_sessions",
            )

        except Exception as e:
            logger.error(f"查询用户会话列表失败: {e}")
            return tool_error_response(
                error=e,
                tool_name="list_user_sessions",
                suggestion="请检查用户 ID 是否正确",
            )


@register_tool(
    group="chat.history",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=[],
    description="根据关键词搜索历史对话内容",
    examples=[
        "搜索包含 Redis 的对话",
        "查找之前关于 K8s 的讨论",
    ],
    enabled=True,
    expose_to_agent=True,
)
class SearchConversationTool(BaseOpTool):
    """搜索对话内容工具"""

    def __init__(self, db=None):
        self.db = db

    async def execute(
        self,
        session_id: Optional[str] = None,
        keyword: str = "",
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        搜索对话内容

        Args:
            session_id: 限制在指定会话中搜索（可选）
            keyword: 搜索关键词
            limit: 返回的匹配消息数量限制

        Returns:
            {
                "success": True,
                "data": {
                    "keyword": str,
                    "matches": int,
                    "messages": [...]
                }
            }
        """
        try:
            db = SessionLocal()

            # 构建查询
            query = db.query(ChatMessage).filter(
                ChatMessage.content.contains(keyword)
            )

            # 限制会话
            if session_id:
                query = query.filter(ChatMessage.session_id == session_id)

            # 按时间倒序
            query = query.order_by(ChatMessage.created_at.desc()).limit(limit)

            messages = query.all()

            # 转换为可读格式
            matches = []
            for msg in messages:
                # 高亮关键词
                highlighted_content = msg.content.replace(
                    keyword,
                    f"**{keyword}**"
                )

                matches.append({
                    "session_id": msg.session_id,
                    "role": msg.role.value,
                    "content": highlighted_content,
                    "created_at": msg.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                })

            db.close()

            return tool_success_response(
                data={
                    "keyword": keyword,
                    "matches": len(matches),
                    "messages": matches,
                },
                tool_name="search_conversation",
            )

        except Exception as e:
            logger.error(f"搜索对话内容失败: {e}")
            return tool_error_response(
                error=e,
                tool_name="search_conversation",
                context={"keyword": keyword},
                suggestion="请检查搜索关键词是否正确",
            )