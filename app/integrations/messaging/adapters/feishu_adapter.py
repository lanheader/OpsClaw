"""
飞书渠道适配器

实现飞书特定的消息处理逻辑。
"""

import base64
import gzip
import hashlib
import json
from typing import Dict, Any, Optional, List

from Crypto.Cipher import AES

from app.utils.logger import get_logger
from app.integrations.messaging.base_channel import (
    BaseChannelAdapter,
    IncomingMessage,
    OutgoingMessage,
    MessageType,
    MessageAction,
)
from app.integrations.feishu.client import get_feishu_client
from app.integrations.feishu.message_formatter import clean_xml_tags
from app.integrations.feishu.message import build_formatted_reply_card

logger = get_logger(__name__)


class FeishuChannelAdapter(BaseChannelAdapter):
    """飞书渠道适配器"""

    channel_type = "feishu"

    # 飞书消息长度限制
    MAX_MESSAGE_LENGTH = 3500

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.client = get_feishu_client()

    async def verify_request(
        self,
        headers: Dict[str, Any],
        body: str
    ) -> bool:
        """
        验证飞书签名

        Args:
            headers: HTTP 请求头
            body: 请求体

        Returns:
            验证是否通过
        """
        timestamp = headers.get("x_lark_request_timestamp", "")
        nonce = headers.get("x_lark_request_nonce", "")
        signature = headers.get("x_lark_signature", "")

        return await self._verify_webhook_signature(
            timestamp=timestamp,
            nonce=nonce,
            body=body,
            signature=signature
        )

    async def _verify_webhook_signature(
        self,
        timestamp: str,
        nonce: str,
        body: str,
        signature: str
    ) -> bool:
        """验证飞书 Webhook 签名"""
        try:
            encrypt_key = self.config.get("verification_token", "")

            # 构造签名串
            sign_str = f"{timestamp}{nonce}{encrypt_key}{body}"
            sign_bytes = sign_str.encode("utf-8")

            # 计算 MD5
            calculated_signature = hashlib.md5(sign_bytes).hexdigest()

            return calculated_signature == signature

        except Exception as e:
            logger.error(f"飞书签名验证失败: {e}")
            return False

    async def decrypt_message(
        self,
        encrypted_data: str
    ) -> Dict[str, Any]:
        """
        解密飞书消息

        Args:
            encrypted_data: 加密的消息字符串

        Returns:
            解密后的消息字典
        """
        encrypt_key = self.config.get("encrypt_key", "")

        try:
            # Base64 解码
            encrypted_bytes = base64.b64decode(encrypted_data)

            # AES 解密
            cipher = AES.new(
                encrypt_key.encode("utf-8")[:16].encode("utf-8"),
                AES.MODE_ECB
            )
            decrypted_bytes = cipher.decrypt(encrypted_bytes)

            # 去除 padding
            padding = decrypted_bytes[-1]
            if isinstance(padding, str):
                padding = ord(padding)
            decrypted_bytes = decrypted_bytes[:-padding]

            # Gzip 解压
            decrypted_str = gzip.decompress(decrypted_bytes).decode("utf-8")

            return json.loads(decrypted_str)

        except Exception as e:
            logger.error(f"飞书消息解密失败: {e}")
            raise

    async def parse_incoming_message(
        self,
        event_data: Dict[str, Any]
    ) -> IncomingMessage:
        """
        解析飞书事件

        Args:
            event_data: 飞书事件数据

        Returns:
            标准化的 IncomingMessage
        """
        header = event_data.get("header", {})
        event = event_data.get("event", {})

        event_type = header.get("event_type", "")

        # 判断操作类型
        if event_type == "card.action.trigger":
            action_type = MessageAction.CARD_CLICK
        elif event_type == "im.message.receive_v1":
            action_type = MessageAction.RECEIVE
        else:
            action_type = MessageAction.COMMAND

        # 提取消息信息
        message = event.get("message", {})
        sender = event.get("sender", {})
        sender_id_info = sender.get("sender_id", {})

        # 提取文本
        text = await self.extract_text(message.get("content", {}))

        incoming_msg = IncomingMessage(
            channel_type=self.channel_type,
            channel_id="feishu_main",
            message_id=message.get("message_id", ""),
            message_type=MessageType.TEXT,
            action_type=action_type,
            sender_id=sender_id_info.get("user_id", ""),
            sender_name=await self.get_user_info(sender_id_info.get("user_id", "")),
            chat_id=message.get("chat_id", ""),
            raw_content=message,
            raw_headers=header,
            text=text,
        )

        return incoming_msg

    async def extract_text(
        self,
        raw_content: Dict[str, Any]
    ) -> str:
        """
        提取飞书消息文本

        Args:
            raw_content: 飞书消息内容

        Returns:
            提取的文本
        """
        if not raw_content:
            return ""

        # 文本消息
        if "text" in raw_content:
            return raw_content.get("text", "")

        # 富文本消息
        if "rich_text" in raw_content:
            elements = raw_content.get("rich_text", {}).get("elements", [])
            texts = []
            for elem in elements:
                if elem.get("type") == "text":
                    text_run = elem.get("text_run", {})
                    texts.append(text_run.get("content", ""))
            return "".join(texts)

        # 交互消息（卡片点击等）
        if "type" in raw_content:
            return raw_content.get("value", "")

        return ""

    async def send_message(
        self,
        message: OutgoingMessage
    ) -> Dict[str, Any]:
        """
        发送飞书消息

        Args:
            message: 标准化的出站消息

        Returns:
            发送结果
        """
        try:
            if message.message_type == MessageType.CARD:
                # 发送卡片
                response = await self.client.send_card_message(
                    message.chat_id,
                    message.content
                )
            else:
                # 发送文本（可能需要分段）
                text = message.content.get("text", "")
                if len(text) > self.MAX_MESSAGE_LENGTH:
                    # 分段发送
                    chunks = self._split_long_text(text, self.MAX_MESSAGE_LENGTH)
                    message_ids = []
                    for chunk in chunks:
                        response = await self.client.send_text_message(
                            message.chat_id,
                            chunk
                        )
                        message_ids.append(response.get("message_id"))
                    return {"message_ids": message_ids}
                else:
                    response = await self.client.send_text_message(
                        message.chat_id,
                        text
                    )

            return response

        except Exception as e:
            logger.error(f"飞书消息发送失败: {e}")
            raise

    async def format_response(
        self,
        content: str,
        message_type: MessageType = MessageType.TEXT
    ) -> Dict[str, Any]:
        """
        格式化飞书响应

        Args:
            content: 消息内容
            message_type: 消息类型

        Returns:
            飞书特定的消息格式
        """
        if message_type == MessageType.CARD:
            # 格式化为卡片
            cleaned = clean_xml_tags(content)
            card = build_formatted_reply_card(content=cleaned)
            return {"card": card.get("card", {})}
        else:
            # 文本消息
            return {"text": content}

    async def add_reaction(
        self,
        message_id: str,
        emoji: str = "ok"
    ) -> bool:
        """
        添加飞书表情回复

        Args:
            message_id: 消息ID
            emoji: 表情符号

        Returns:
            是否成功
        """
        try:
            await self.client.add_message_reaction(message_id, emoji)
            return True
        except Exception as e:
            logger.warning(f"添加飞书表情失败: {e}")
            return False

    async def get_user_info(
        self,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取飞书用户信息

        Args:
            user_id: 用户ID

        Returns:
            用户信息字典
        """
        try:
            user_info = await self.client.get_user_info(user_id)
            return {
                "name": user_info.get("name", ""),
                "avatar": user_info.get("avatar", ""),
                "email": user_info.get("email", ""),
            }
        except Exception as e:
            logger.warning(f"获取飞书用户信息失败: {e}")
            return None

    def _split_long_text(
        self,
        text: str,
        max_length: int
    ) -> List[str]:
        """
        分割长文本

        Args:
            text: 原始文本
            max_length: 最大长度

        Returns:
            分割后的文本列表
        """
        if len(text) <= max_length:
            return [text]

        chunks = []
        current_chunk = ""

        # 按行分割
        lines = text.split("\n")

        for line in lines:
            # 如果当前行加上当前块超过限制
            if len(current_chunk) + len(line) + 1 > max_length:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = line
            else:
                if current_chunk:
                    current_chunk += "\n" + line
                else:
                    current_chunk = line

        # 添加最后一块
        if current_chunk:
            chunks.append(current_chunk)

        return chunks


def create_feishu_adapter(config: Dict[str, Any]) -> FeishuChannelAdapter:
    """
    创建飞书适配器（工厂函数）

    Args:
        config: 配置字典

    Returns:
        飞书适配器实例
    """
    return FeishuChannelAdapter(config)
