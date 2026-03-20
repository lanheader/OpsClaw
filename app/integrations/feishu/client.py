# app/integrations/feishu/client.py
"""用于消息发送和 API 交互的飞书客户端"""

import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import httpx
from app.utils.logger import get_logger

logger = get_logger(__name__)


class FeishuClient:
    """
    用于与飞书（Lark）API 交互的客户端。

    支持：
    - Webhook 和长连接两种模式
    - 租户访问令牌管理（带缓存）
    - 文本和卡片消息发送
    - 群聊信息查询
    - 健康检查
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        webhook_url: Optional[str] = None,
        verification_token: Optional[str] = None,
        encrypt_key: Optional[str] = None,
        connection_mode: str = "webhook",
    ):
        """
        初始化飞书客户端。

        参数：
            app_id: 飞书应用 ID
            app_secret: 飞书应用密钥
            webhook_url: 可选的 Webhook URL（用于简单消息发送）
            verification_token: 可选的验证令牌（用于签名验证）
            encrypt_key: 可选的加密密钥（用于消息加解密）
            connection_mode: 连接模式（webhook、longconn 或 auto）
        """
        self.app_id = app_id
        self.app_secret = app_secret
        self.webhook_url = webhook_url
        self.verification_token = verification_token
        self.encrypt_key = encrypt_key
        self.connection_mode = connection_mode

        self._client = httpx.AsyncClient(timeout=30)
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

        self.base_url = "https://open.feishu.cn/open-apis"

        logger.info(
            f"FeishuClient initialized: mode={connection_mode}, "
            f"has_webhook={webhook_url is not None}"
        )

    async def get_access_token(self) -> str:
        """
        获取租户访问令牌（tenant_access_token）。

        实现了令牌缓存，仅在过期时才重新获取。

        返回：
            有效的访问令牌

        异常：
            RuntimeError: 如果获取令牌失败

        示例：
            token = await client.get_access_token()
        """
        # 检查缓存是否有效
        if self._access_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at:
                logger.debug("Using cached access token")
                return self._access_token

        # 获取新令牌
        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        payload = {"app_id": self.app_id, "app_secret": self.app_secret}

        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != 0:
                error_msg = data.get("msg", "Unknown error")
                logger.error(f"Failed to get access token: {error_msg}")
                raise RuntimeError(f"Feishu API error: {error_msg}")

            # 缓存令牌（默认 2 小时有效期，提前 5 分钟刷新）
            self._access_token = data["tenant_access_token"]
            expire_seconds = data.get("expire", 7200) - 300  # 提前 5 分钟
            self._token_expires_at = datetime.now() + timedelta(seconds=expire_seconds)

            logger.info(f"Access token acquired, expires at {self._token_expires_at}")
            return self._access_token

        except httpx.HTTPError as e:
            logger.exception(f"HTTP error getting access token: {e}")
            raise RuntimeError(f"Failed to get Feishu access token: {e}")
        except Exception as e:
            logger.exception(f"Error getting access token: {e}")
            raise RuntimeError(f"Unexpected error: {e}")

    async def send_text_message(self, chat_id: str, text: str) -> Dict[str, Any]:
        """
        发送文本消息到群聊。

        参数：
            chat_id: 群聊 ID（chat_id 或 open_id）
            text: 消息文本内容

        返回：
            包含发送结果的字典

        示例：
            result = await client.send_text_message(
                chat_id="oc_xxx",
                text="Hello from Ops Agent!"
            )
        """
        url = f"{self.base_url}/im/v1/messages"
        token = await self.get_access_token()

        params = {"receive_id_type": "chat_id"}

        # 使用 json.dumps 正确序列化 content，避免特殊字符问题
        content = json.dumps({"text": text}, ensure_ascii=False)

        payload = {"receive_id": chat_id, "msg_type": "text", "content": content}

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        try:
            response = await self._client.post(url, params=params, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != 0:
                logger.error(f"Failed to send text message: {data.get('msg')}")
            else:
                logger.info(f"Text message sent successfully to {chat_id}")

            return data

        except httpx.HTTPError as e:
            logger.exception(f"HTTP error sending text message: {e}")
            return {"code": -1, "msg": str(e)}
        except Exception as e:
            logger.exception(f"Error sending text message: {e}")
            return {"code": -1, "msg": str(e)}

    async def send_card_message(self, chat_id: str, card: Dict[str, Any]) -> Dict[str, Any]:
        """
        发送卡片消息到群聊。

        参数：
            chat_id: 群聊 ID
            card: 卡片内容（JSON 格式）

        返回：
            包含发送结果的字典

        示例：
            card = {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": "通知"},
                    "template": "blue"
                },
                "elements": [...]
            }
            result = await client.send_card_message(chat_id, card)
        """
        url = f"{self.base_url}/im/v1/messages"
        token = await self.get_access_token()

        params = {"receive_id_type": "chat_id"}

        # 将卡片内容转换为字符串
        card_content = json.dumps(card, ensure_ascii=False)

        payload = {"receive_id": chat_id, "msg_type": "interactive", "content": card_content}

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        try:
            response = await self._client.post(url, params=params, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != 0:
                logger.error(f"Failed to send card message: {data.get('msg')}")
            else:
                logger.info(f"Card message sent successfully to {chat_id}")

            return data

        except httpx.HTTPError as e:
            logger.exception(f"HTTP error sending card message: {e}")
            return {"code": -1, "msg": str(e)}
        except Exception as e:
            logger.exception(f"Error sending card message: {e}")
            return {"code": -1, "msg": str(e)}

    async def add_message_reaction(
        self, message_id: str, emoji_type: str = "THUMBSUP"
    ) -> Dict[str, Any]:
        """
        为消息添加表情回复（reaction）

        参数：
            message_id: 消息 ID（如 om_xxx）
            emoji_type: 表情类型，常用值：
                - THUMBSUP: 👍
                - OK: 👌
                - HEART: ❤️
                - CLAP: 👏
                - CHECK: ✅
                - SMILE: 😄
                - CELEBRATE: 🎉
                - ROCKET: 🚀

        返回：
            API 响应数据

        示例：
            result = await client.add_message_reaction("om_xxx", "OK")
        """
        token = await self.get_access_token()

        url = f"{self.base_url}/im/v1/messages/{message_id}/reactions"

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        payload = {"reaction_type": {"emoji_type": emoji_type}}

        try:
            response = await self._client.post(url, headers=headers, json=payload)
            data = response.json()

            if data.get("code") != 0:
                logger.error(f"Failed to add reaction: {data.get('msg')}")
            else:
                logger.debug(f"Added reaction {emoji_type} to message {message_id}")

            return data

        except httpx.HTTPError as e:
            logger.exception(f"HTTP error adding reaction: {e}")
            return {"code": -1, "msg": str(e)}
        except Exception as e:
            logger.exception(f"Error adding reaction: {e}")
            return {"code": -1, "msg": str(e)}

    async def send_webhook_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        通过 Webhook 发送消息（更简单，无需令牌）。

        参数：
            message: 消息内容（可以是文本或卡片）

        返回：
            包含发送结果的字典

        示例：
            result = await client.send_webhook_message({
                "msg_type": "text",
                "content": {"text": "Hello!"}
            })
        """
        if not self.webhook_url:
            logger.error("Webhook URL not configured")
            return {"code": -1, "msg": "Webhook URL not configured"}

        try:
            response = await self._client.post(self.webhook_url, json=message)
            response.raise_for_status()
            data = response.json()

            if data.get("StatusCode") != 0:
                logger.error(f"Webhook message failed: {data.get('StatusMessage')}")
            else:
                logger.info("Webhook message sent successfully")

            return data

        except httpx.HTTPError as e:
            logger.exception(f"HTTP error sending webhook message: {e}")
            return {"code": -1, "msg": str(e)}
        except Exception as e:
            logger.exception(f"Error sending webhook message: {e}")
            return {"code": -1, "msg": str(e)}

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """
        获取群聊信息。

        参数：
            chat_id: 群聊 ID

        返回：
            包含群聊信息的字典

        示例：
            info = await client.get_chat_info("oc_xxx")
        """
        url = f"{self.base_url}/im/v1/chats/{chat_id}"
        token = await self.get_access_token()

        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = await self._client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != 0:
                logger.error(f"Failed to get chat info: {data.get('msg')}")

            return data

        except httpx.HTTPError as e:
            logger.exception(f"HTTP error getting chat info: {e}")
            return {"code": -1, "msg": str(e)}
        except Exception as e:
            logger.exception(f"Error getting chat info: {e}")
            return {"code": -1, "msg": str(e)}

    async def check_feishu_health(self) -> bool:
        """
        检查飞书 API 是否健康且可访问。

        返回：
            如果飞书 API 可访问则返回 True，否则返回 False

        示例：
            is_healthy = await client.check_feishu_health()
        """
        try:
            # 尝试获取访问令牌作为健康检查
            await self.get_access_token()
            return True
        except Exception as e:
            logger.error(f"Feishu health check failed: {e}")
            return False

    async def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        获取用户信息

        参数：
            user_id: 用户 ID（open_id 或 user_id）

        返回：
            用户信息字典，包含 name, en_name, avatar 等字段
            如果获取失败，返回 None

        示例：
            user_info = await client.get_user_info("ou_xxxxx")
            if user_info:
                print(f"User name: {user_info.get('name')}")
        """
        url = f"{self.base_url}/contact/v3/users/{user_id}"
        token = await self.get_access_token()

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        params = {"user_id_type": "open_id"}  # 使用 open_id 类型

        try:
            response = await self._client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != 0:
                logger.warning(f"Failed to get user info for {user_id}: {data.get('msg')}")
                return None

            user_data = data.get("data", {}).get("user", {})
            logger.debug(f"Got user info for {user_id}: {user_data.get('name')}")
            return user_data

        except httpx.HTTPError as e:
            logger.warning(f"HTTP error getting user info: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error getting user info: {e}")
            return None

    async def close(self):
        """关闭 HTTP 客户端"""
        await self._client.aclose()
        logger.info("FeishuClient closed")

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()


# 单例实例
_feishu_client: Optional[FeishuClient] = None


def get_feishu_client() -> FeishuClient:
    """
    获取单例 FeishuClient 实例。

    返回：
        FeishuClient 实例

    异常：
        RuntimeError: 如果飞书集成未启用

    示例：
        client = get_feishu_client()
        await client.send_text_message(chat_id, "Hello!")
    """
    global _feishu_client

    if _feishu_client is None:
        from app.core.config import get_settings

        settings = get_settings()

        if not settings.FEISHU_ENABLED:
            raise RuntimeError("Feishu integration is not enabled")

        _feishu_client = FeishuClient(
            app_id=settings.FEISHU_APP_ID,
            app_secret=settings.FEISHU_APP_SECRET,
            webhook_url=settings.FEISHU_WEBHOOK_URL,
            verification_token=settings.FEISHU_VERIFICATION_TOKEN,
            encrypt_key=settings.FEISHU_ENCRYPT_KEY,
            connection_mode=settings.FEISHU_CONNECTION_MODE,
        )

    return _feishu_client
