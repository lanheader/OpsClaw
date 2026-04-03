"""
消息渠道适配器基类

定义统一的消息处理接口，支持多种消息渠道（飞书、Slack、微信、钉钉等）。

所有渠道适配器必须实现此接口，确保统一的处理流程。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, field


class MessageType(str, Enum):
    """消息类型枚举"""
    TEXT = "text"
    CARD = "card"
    IMAGE = "image"
    FILE = "file"
    INTERACTIVE = "interactive"


class MessageAction(str, Enum):
    """消息操作类型"""
    RECEIVE = "receive"           # 接收消息
    CARD_CLICK = "card_click"     # 卡片点击
    COMMAND = "command"           # 命令（如 /help）
    APPROVAL = "approval"         # 审批操作


@dataclass
class IncomingMessage:
    """
    统一的消息入站格式

    将不同渠道的消息转换为统一格式，便于后续处理。
    """
    # 渠道信息
    channel_type: str              # 渠道类型：feishu, slack, wechat, dingtalk
    channel_id: str                # 渠道唯一标识

    # 消息内容
    message_id: str                # 消息唯一ID
    message_type: MessageType      # 消息类型
    action_type: MessageAction     # 操作类型

    # 用户信息
    sender_id: str                 # 发送者ID
    sender_name: Optional[str]     # 发送者名称
    chat_id: str                   # 会话ID

    # 原始数据
    raw_content: Dict[str, Any]    # 原始消息内容
    raw_headers: Dict[str, Any]    # 原始请求头（用于签名验证）

    # 提取的文本
    text: str                      # 提取的文本内容

    # 扩展字段
    metadata: Dict[str, Any] = field(default_factory=dict)  # 其他元数据


@dataclass
class OutgoingMessage:
    """
    统一的消息出站格式

    将统一格式转换为各渠道特定的消息格式。
    """
    chat_id: str                   # 目标会话ID
    message_type: MessageType      # 消息类型
    content: Dict[str, Any]        # 消息内容（文本或卡片）

    # 可选字段
    message_id: Optional[str] = None      # 回复的消息ID
    parent_id: Optional[str] = None       # 父消息ID（用于 threaded 回复）
    metadata: Optional[Dict[str, Any]] = None  # 元数据


class ChannelContext:
    """
    渠道上下文信息

    在整个消息处理流程中传递，包含会话、用户等信息。
    """

    def __init__(
        self,
        channel_type: str,
        chat_id: str,
        sender_id: str,
        session_id: Optional[str] = None,
        user_id: Optional[int] = None,
        user_permissions: Optional[set] = None,
        message_id: Optional[str] = None,  # 原始消息ID，用于添加表情回复
    ):
        self.channel_type = channel_type
        self.chat_id = chat_id
        self.sender_id = sender_id
        self.session_id = session_id
        self.user_id = user_id
        self.user_permissions = user_permissions or set()
        self.message_id = message_id  # 保存原始消息ID
        self.metadata = {}  # type: ignore[var-annotated]

    def has_permission(self, permission: str) -> bool:
        """检查用户是否有指定权限"""
        return permission in self.user_permissions

    def add_permissions(self, permissions: List[str]) -> None:
        """添加权限"""
        self.user_permissions.update(permissions)


class BaseChannelAdapter(ABC):
    """
    消息渠道适配器基类

    所有渠道适配器必须实现此接口，确保统一的处理流程。

    设计原则：
    1. 单一职责：只负责与渠道的 API 交互
    2. 统一接口：所有渠道实现相同的接口
    3. 易于扩展：添加新渠道只需实现此基类
    """

    # 渠道类型标识（子类必须覆盖）
    channel_type: str = None  # type: ignore[assignment]

    def __init__(self, config: Dict[str, Any] = None):  # type: ignore[assignment]
        """
        初始化适配器

        Args:
            config: 渠道配置，如 API 密钥、端点 URL 等
        """
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)

    @abstractmethod
    async def verify_request(self, headers: Dict[str, Any], body: str) -> bool:
        """
        验证请求签名（渠道特定）

        Args:
            headers: HTTP 请求头
            body: 请求体（字符串）

        Returns:
            bool: 验证是否通过

        示例:
            飞书：验证 x_lark_signature
            Slack：验证 x-slack-signature
            微信：验证签名
        """
        pass

    @abstractmethod
    async def decrypt_message(self, encrypted_data: str) -> Dict[str, Any]:
        """
        解密消息（渠道特定）

        Args:
            encrypted_data: 加密的消息数据

        Returns:
            解密后的消息字典

        注意：
            不是所有渠道都加密消息，如果不加密则直接返回解析后的数据
        """
        pass

    @abstractmethod
    async def parse_incoming_message(
        self,
        event_data: Dict[str, Any]
    ) -> IncomingMessage:
        """
        解析入站消息（渠道特定）

        将渠道特定的事件格式转换为统一的 IncomingMessage

        Args:
            event_data: 渠道事件数据

        Returns:
            标准化的 IncomingMessage

        示例:
            飞书：im.message.receive_v1 事件
            Slack：message 事件
            微信：文本消息事件
        """
        pass

    @abstractmethod
    async def send_message(self, message: OutgoingMessage) -> Dict[str, Any]:
        """
        发送消息（渠道特定）

        Args:
            message: 标准化的出站消息

        Returns:
            发送结果字典，通常包含 message_id 等

        注意:
            应该处理消息分段（长消息拆分）
            应该处理错误重试
        """
        pass

    @abstractmethod
    async def format_response(
        self,
        content: str,
        message_type: MessageType = MessageType.TEXT
    ) -> Dict[str, Any]:
        """
        格式化响应消息（渠道特定）

        Args:
            content: 消息内容
            message_type: 消息类型

        Returns:
            渠道特定的消息格式

        示例:
            飞书：返回 card 或 text 对象
            Slack：返回 blocks 或 text
        """
        pass

    # 可选方法（提供默认实现）

    async def extract_text(self, raw_content: Dict[str, Any]) -> str:
        """
        提取文本内容（渠道特定，有默认实现）

        Args:
            raw_content: 原始消息内容

        Returns:
            提取的文本

        默认实现：
            直接返回 raw_content.get("text", "")
        """
        return raw_content.get("text", "")  # type: ignore[no-any-return]

    async def add_reaction(
        self,
        message_id: str,
        emoji: str = "ok"
    ) -> bool:
        """
        添加表情回复（可选功能）

        Args:
            message_id: 消息ID
            emoji: 表情符号

        Returns:
            是否成功

        默认实现：
            返回 False（不支持）
        """
        return False

    async def get_user_info(
        self,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取用户信息（可选功能）

        Args:
            user_id: 用户ID

        Returns:
            用户信息字典，包含 name、avatar 等

        默认实现：
            返回 None（不支持）
        """
        return None

    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            健康状态信息

        示例:
            {
                "channel_type": "feishu",
                "enabled": True,
                "healthy": True,
                "latency_ms": 50
            }
        """
        return {
            "channel_type": self.channel_type,
            "enabled": self.enabled,
            "healthy": True
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(channel_type={self.channel_type}, enabled={self.enabled})"
