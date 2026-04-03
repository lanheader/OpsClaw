# app/models/login_history.py
"""登录历史模型"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.models.database import Base


class LoginHistory(Base):
    """登录历史模型"""

    __tablename__ = "login_history"

    # 主键
    id = Column(Integer, primary_key=True, index=True)

    # 外键
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="用户ID")

    # 登录信息
    login_time = Column(DateTime, default=datetime.utcnow, comment="登录时间")
    ip_address = Column(String(45), nullable=True, comment="IP地址（支持IPv6）")
    user_agent = Column(String(500), nullable=True, comment="User-Agent")
    login_status = Column(String(20), nullable=False, comment="登录状态：success/failed")
    failure_reason = Column(String(200), nullable=True, comment="失败原因")

    # 关系
    user = relationship("User", backref="login_history")

    def __repr__(self):  # type: ignore[no-untyped-def]
        return f"<LoginHistory(id={self.id}, user_id={self.user_id}, status='{self.login_status}')>"
