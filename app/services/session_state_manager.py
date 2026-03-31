"""会话状态管理服务"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
import logging
import time

from app.models.chat_session import ChatSession, SessionState
from app.models.database import SessionLocal

logger = logging.getLogger(__name__)


def _retry_on_db_lock(max_retries: int = 3, delay: float = 0.1):
    """重试装饰器，处理数据库锁定错误

    注意：此装饰器用于同步函数。如果在异步上下文中调用被装饰的函数，
    建议使用 asyncio.to_thread() 或 run_in_executor() 来避免阻塞事件循环。
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    if "database is locked" in str(e) and attempt < max_retries - 1:
                        logger.warning(f"数据库锁定，重试 {attempt + 1}/{max_retries}...")
                        time.sleep(delay * (attempt + 1))
                    else:
                        raise
            return None
        return wrapper
    return decorator


class SessionStateManager:
    """会话状态管理器"""

    @staticmethod
    def set_awaiting_approval(
        session_id: str, approval_data: Dict[str, Any], timeout_minutes: int = 5
    ) -> bool:
        """
        设置会话为等待批准状态

        Args:
            session_id: 会话ID
            approval_data: 批准数据（包含命令、风险等级等）
            timeout_minutes: 超时时间（分钟）- 仅用于记录，不做自动清理

        Returns:
            是否设置成功
        """
        db = SessionLocal()
        try:
            session = db.query(ChatSession).filter_by(session_id=session_id).first()
            if not session:
                logger.error(f"会话不存在: {session_id}")
                return False

            # 设置状态
            session.state = SessionState.AWAITING_APPROVAL.value
            session.pending_approval_data = approval_data
            # 记录过期时间，但不用于自动清理，仅供参考
            session.approval_expires_at = datetime.now(timezone.utc) + timedelta(
                minutes=timeout_minutes
            )

            db.commit()
            logger.info(f"会话 {session_id} 已设置为等待批准状态")
            return True

        except Exception as e:
            logger.error(f"设置会话状态失败: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    @staticmethod
    def check_awaiting_approval(session_id: str) -> Optional[Dict[str, Any]]:
        """
        检查会话是否在等待批准状态

        Args:
            session_id: 会话ID

        Returns:
            如果在等待批准，返回批准数据；否则返回 None
        """
        db = SessionLocal()
        try:
            logger.info(f"检查会话状态: session_id={session_id}")

            session = db.query(ChatSession).filter_by(session_id=session_id).first()
            if not session:
                logger.warning(f"会话不存在: session_id={session_id}")
                return None

            logger.info(f"  会话状态: {session.state}")
            logger.info(f"  批准数据存在: {session.pending_approval_data is not None}")
            logger.info(f"  过期时间: {session.approval_expires_at}")

            # 检查状态
            if session.state != SessionState.AWAITING_APPROVAL.value:
                logger.warning(f"会话状态不是 awaiting_approval: {session.state}")
                return None

            # 不检查过期时间，因为状态由用户操作驱动
            # 只要状态是 awaiting_approval，就返回批准数据
            logger.info(f"会话处于等待批准状态，返回批准数据")
            return session.pending_approval_data

        except Exception as e:
            logger.error(f"检查会话状态失败: {e}", exc_info=True)
            return None
        finally:
            db.close()

    @staticmethod
    def set_processing(session_id: str) -> bool:
        """
        设置会话为处理中状态

        Args:
            session_id: 会话ID

        Returns:
            是否设置成功
        """
        db = SessionLocal()
        try:
            session = db.query(ChatSession).filter_by(session_id=session_id).first()
            if not session:
                return False

            session.state = SessionState.PROCESSING.value
            db.commit()
            logger.info(f"会话 {session_id} 已设置为处理中状态")
            return True

        except Exception as e:
            logger.error(f"设置会话状态失败: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    @staticmethod
    def reset_to_normal(session_id: str) -> bool:
        """
        重置会话为正常状态

        Args:
            session_id: 会话ID

        Returns:
            是否重置成功
        """
        db = SessionLocal()
        try:
            session = db.query(ChatSession).filter_by(session_id=session_id).first()
            if not session:
                return False

            session.state = SessionState.NORMAL.value
            session.pending_approval_data = None
            session.approval_expires_at = None

            db.commit()
            logger.info(f"会话 {session_id} 已重置为正常状态")
            return True

        except Exception as e:
            logger.error(f"重置会话状态失败: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    @staticmethod
    def get_session_by_external_chat_id(external_chat_id: str) -> Optional[ChatSession]:
        """
        通过外部聊天ID获取会话

        Args:
            external_chat_id: 外部聊天ID（如飞书chat_id）

        Returns:
            会话对象，如果不存在则返回 None
        """
        db = SessionLocal()
        try:
            session = (
                db.query(ChatSession)
                .filter_by(external_chat_id=external_chat_id, is_active=True)
                .first()
            )
            return session
        finally:
            db.close()

    # 移除 cleanup_expired_approvals 方法，因为不需要定时清理
    # 状态由用户的批准/拒绝操作来改变

    @staticmethod
    def get_last_processed_message_index(session_id: str) -> int:
        """
        获取会话已处理的消息索引

        Args:
            session_id: 会话ID

        Returns:
            已处理的消息索引，如果会话不存在则返回 -1
        """
        db = SessionLocal()
        try:
            session = db.query(ChatSession).filter_by(session_id=session_id).first()
            if not session:
                return -1
            return session.last_processed_message_index or -1
        except Exception as e:
            logger.error(f"获取已处理消息索引失败: {e}")
            return -1
        finally:
            db.close()

    @staticmethod
    @_retry_on_db_lock(max_retries=3, delay=0.1)
    def set_last_processed_message_index(session_id: str, index: int) -> bool:
        """
        设置会话已处理的消息索引（带重试机制）

        Args:
            session_id: 会话ID
            index: 已处理的消息索引

        Returns:
            是否设置成功
        """
        db = SessionLocal()
        try:
            session = db.query(ChatSession).filter_by(session_id=session_id).first()
            if not session:
                logger.error(f"会话不存在: {session_id}")
                return False

            # ✅ 修复：允许更新为相同或更大的索引
            # 原因：工作流最后一条消息的索引可能等于 last_processed
            # 之前的条件 (>) 会导致最后一条消息被跳过
            if index >= (session.last_processed_message_index or -1):
                session.last_processed_message_index = index
                db.commit()
                logger.debug(f"会话 {session_id} 已处理消息索引更新为 {index}")
            return True

        except Exception as e:
            logger.error(f"设置已处理消息索引失败: {e}")
            db.rollback()
            return False
        finally:
            db.close()
