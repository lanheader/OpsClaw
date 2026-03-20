"""会话状态管理服务"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
import logging

from app.models.chat_session import ChatSession, SessionState
from app.models.database import SessionLocal

logger = logging.getLogger(__name__)


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
            session.approval_expires_at = datetime.utcnow() + timedelta(minutes=timeout_minutes)

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
            logger.info(f"🔍 检查会话状态: session_id={session_id}")

            session = db.query(ChatSession).filter_by(session_id=session_id).first()
            if not session:
                logger.warning(f"⚠️ 会话不存在: session_id={session_id}")
                return None

            logger.info(f"   会话状态: {session.state}")
            logger.info(f"   批准数据存在: {session.pending_approval_data is not None}")
            logger.info(f"   过期时间: {session.approval_expires_at}")

            # 检查状态
            if session.state != SessionState.AWAITING_APPROVAL.value:
                logger.warning(f"⚠️ 会话状态不是 awaiting_approval: {session.state}")
                return None

            # 不检查过期时间，因为状态由用户操作驱动
            # 只要状态是 awaiting_approval，就返回批准数据
            logger.info(f"✅ 会话处于等待批准状态，返回批准数据")
            return session.pending_approval_data

        except Exception as e:
            logger.error(f"❌ 检查会话状态失败: {e}", exc_info=True)
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
