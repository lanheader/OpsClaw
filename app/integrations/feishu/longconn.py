# app/integrations/feishu/longconn.py
"""飞书 WebSocket 长连接管理器"""

import asyncio
import json
from typing import Optional, Callable, Dict, Any
from datetime import datetime

import websockets
from websockets.client import WebSocketClientProtocol
import httpx
from app.utils.logger import get_logger

logger = get_logger(__name__)


class FeishuLongConnManager:
    """
    飞书 WebSocket 长连接管理器。

    支持：
    - WebSocket 连接建立和维护
    - 心跳保持
    - 断线自动重连
    - 事件接收和分发
    - 事件处理器注册
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        heartbeat_interval: int = 30,
        reconnect_interval: int = 5,
        max_reconnect_attempts: int = 10,
    ):
        """
        初始化长连接管理器。

        参数：
            app_id: 飞书应用 ID
            app_secret: 飞书应用密钥
            heartbeat_interval: 心跳间隔（秒）
            reconnect_interval: 重连间隔（秒）
            max_reconnect_attempts: 最大重连次数
        """
        self.app_id = app_id
        self.app_secret = app_secret
        self.heartbeat_interval = heartbeat_interval
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_attempts = max_reconnect_attempts

        self._ws: Optional[WebSocketClientProtocol] = None
        self._running = False
        self._reconnect_count = 0
        self._last_heartbeat: Optional[datetime] = None
        self._event_handlers: Dict[str, Callable] = {}
        self._tasks: list = []

        logger.info(
            f"FeishuLongConnManager initialized: "
            f"heartbeat_interval={heartbeat_interval}s, "
            f"max_reconnect_attempts={max_reconnect_attempts}"
        )

    async def connect(self):
        """
        建立 WebSocket 长连接。

        步骤：
        1. 获取 WebSocket endpoint URL
        2. 建立 WebSocket 连接
        3. 启动心跳和消息接收循环
        """
        logger.info("Starting Feishu WebSocket long connection...")

        try:
            # 获取 WebSocket endpoint
            endpoint = await self._get_websocket_endpoint()

            # 建立连接
            self._ws = await websockets.connect(
                endpoint, ping_interval=None, close_timeout=10  # 禁用自动 ping，使用自定义心跳
            )

            self._running = True
            self._reconnect_count = 0

            logger.info(f"WebSocket connected: {endpoint}")

            # 启动心跳和接收循环
            self._tasks = [
                asyncio.create_task(self._heartbeat_loop(), name="heartbeat"),
                asyncio.create_task(self._receive_loop(), name="receive"),
            ]

            # 等待任务完成（通常不会主动完成，除非出错）
            await asyncio.gather(*self._tasks, return_exceptions=True)

        except Exception as e:
            logger.exception(f"Error in WebSocket connection: {e}")
            await self._reconnect()

    async def _get_websocket_endpoint(self) -> str:
        """
        获取 WebSocket 连接端点 URL。

        飞书长连接 API 文档：
        https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/event-subscription-guide/event-subscription-configure-/request-url-configuration

        返回：
            WebSocket endpoint URL

        异常：
            RuntimeError: 如果获取失败
        """
        from app.integrations.feishu.client import FeishuClient

        # 创建临时客户端获取 token
        client = FeishuClient(app_id=self.app_id, app_secret=self.app_secret)

        try:
            token = await client.get_access_token()

            async with httpx.AsyncClient(timeout=30) as http_client:
                # 正确的长连接 API 端点
                response = await http_client.post(
                    "https://open.feishu.cn/open-apis/im/v1/stream/get",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    json={},  # 不需要传 app_id，token 中已包含
                )
                response.raise_for_status()
                data = response.json()

                if data.get("code") != 0:
                    error_msg = data.get("msg", "Unknown error")
                    error_code = data.get("code")
                    raise RuntimeError(
                        f"Failed to get WebSocket endpoint: code={error_code}, msg={error_msg}"
                    )

                endpoint = data["data"]["url"]
                logger.info(f"Got WebSocket endpoint: {endpoint}")

                return endpoint

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error getting WebSocket endpoint: {e.response.status_code} {e.response.text}"
            )
            raise RuntimeError(f"Failed to get WebSocket endpoint: {e}")
        except Exception as e:
            logger.exception(f"Error getting WebSocket endpoint: {e}")
            raise RuntimeError(f"Failed to get WebSocket endpoint: {e}")
        finally:
            await client.close()

    async def _heartbeat_loop(self):
        """
        心跳循环。

        定期发送 ping 消息保持连接。
        """
        logger.info("Heartbeat loop started")

        while self._running:
            try:
                if self._ws and not self._ws.closed:
                    # 发送 ping
                    await self._ws.ping()
                    self._last_heartbeat = datetime.now()
                    logger.debug(f"Heartbeat sent at {self._last_heartbeat}")

                    await asyncio.sleep(self.heartbeat_interval)
                else:
                    logger.warning("WebSocket not connected, stopping heartbeat")
                    break

            except asyncio.CancelledError:
                logger.info("Heartbeat loop cancelled")
                break
            except Exception as e:
                logger.exception(f"Heartbeat error: {e}")
                await self._reconnect()
                break

    async def _receive_loop(self):
        """
        消息接收循环。

        持续接收和处理 WebSocket 消息。
        """
        logger.info("Receive loop started")

        while self._running:
            try:
                if self._ws and not self._ws.closed:
                    # 接收消息
                    message = await self._ws.recv()
                    logger.debug(f"Received message: {message[:200]}...")

                    # 处理消息
                    await self._handle_message(message)
                else:
                    logger.warning("WebSocket not connected, stopping receive loop")
                    break

            except asyncio.CancelledError:
                logger.info("Receive loop cancelled")
                break
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket connection closed")
                await self._reconnect()
                break
            except Exception as e:
                logger.exception(f"Receive loop error: {e}")
                await asyncio.sleep(1)  # 短暂延迟后继续

    async def _handle_message(self, message: str):
        """
        处理接收到的 WebSocket 消息。

        参数：
            message: JSON 格式的消息字符串
        """
        try:
            # 解析 JSON
            data = json.loads(message)

            # 获取消息类型
            msg_type = data.get("type")

            # 系统消息（如连接确认、心跳响应）
            if msg_type == "pong":
                logger.debug("Received pong response")
                return

            # 事件消息
            event_type = data.get("header", {}).get("event_type")

            if event_type:
                logger.info(f"Received event: {event_type}")

                # 分发到注册的处理器
                handler = self._event_handlers.get(event_type)
                if handler:
                    try:
                        await handler(data)
                    except Exception as e:
                        logger.exception(f"Error in event handler for {event_type}: {e}")
                else:
                    logger.debug(f"No handler registered for event type: {event_type}")
            else:
                logger.debug(f"Received message without event_type: {msg_type}")

        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON message: {message[:200]}...")
        except Exception as e:
            logger.exception(f"Error handling message: {e}")

    async def _reconnect(self):
        """
        重新连接 WebSocket。

        实现指数退避重连策略。
        """
        if self._reconnect_count >= self.max_reconnect_attempts:
            logger.error(
                f"Max reconnection attempts ({self.max_reconnect_attempts}) reached, giving up"
            )
            self._running = False
            return

        self._reconnect_count += 1

        # 指数退避：2^n 秒，最大 60 秒
        delay = min(2**self._reconnect_count, 60)

        logger.info(
            f"Reconnecting in {delay}s... "
            f"(attempt {self._reconnect_count}/{self.max_reconnect_attempts})"
        )

        await asyncio.sleep(delay)

        try:
            # 取消现有任务
            for task in self._tasks:
                if not task.done():
                    task.cancel()

            # 关闭旧连接
            if self._ws and not self._ws.closed:
                await self._ws.close()

            # 重新连接
            await self.connect()

        except Exception as e:
            logger.exception(f"Reconnection failed: {e}")
            await self._reconnect()

    def register_handler(self, event_type: str, handler: Callable):
        """
        注册事件处理器。

        参数：
            event_type: 事件类型（如 "card.action.trigger"）
            handler: 异步处理函数，接收事件数据作为参数

        示例：
            async def my_handler(data: Dict[str, Any]):
                print(f"Received event: {data}")

            manager.register_handler("im.message.receive_v1", my_handler)
        """
        self._event_handlers[event_type] = handler
        logger.info(f"Registered handler for event type: {event_type}")

    def unregister_handler(self, event_type: str):
        """
        注销事件处理器。

        参数：
            event_type: 事件类型
        """
        if event_type in self._event_handlers:
            del self._event_handlers[event_type]
            logger.info(f"Unregistered handler for event type: {event_type}")

    async def close(self):
        """
        关闭 WebSocket 连接。

        停止心跳和接收循环，关闭连接。
        """
        logger.info("Closing WebSocket connection...")

        self._running = False

        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # 等待任务结束
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        # 关闭 WebSocket
        if self._ws and not self._ws.closed:
            await self._ws.close()

        logger.info("WebSocket connection closed")

    def is_connected(self) -> bool:
        """
        检查是否已连接。

        返回：
            如果连接正常则返回 True
        """
        return self._ws is not None and not self._ws.closed and self._running

    def get_status(self) -> Dict[str, Any]:
        """
        获取长连接状态信息。

        返回：
            包含状态信息的字典
        """
        return {
            "connected": self.is_connected(),
            "running": self._running,
            "reconnect_count": self._reconnect_count,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
            "registered_handlers": list(self._event_handlers.keys()),
        }


# 全局长连接管理器实例
_longconn_manager: Optional[FeishuLongConnManager] = None


async def start_longconn():
    """
    启动飞书 WebSocket 长连接（后台任务）。

    从配置中读取参数并启动长连接管理器。
    注册默认的事件处理器。
    """
    global _longconn_manager

    from app.core.config import get_settings

    settings = get_settings()

    # 检查是否启用长连接模式
    if settings.FEISHU_CONNECTION_MODE not in ["longconn", "auto"]:
        logger.info(f"Long connection mode not enabled (mode={settings.FEISHU_CONNECTION_MODE})")
        return

    if not settings.FEISHU_ENABLED:
        logger.warning("Feishu integration not enabled, skipping long connection")
        return

    logger.info("Starting Feishu long connection...")

    try:
        # 创建长连接管理器
        _longconn_manager = FeishuLongConnManager(
            app_id=settings.FEISHU_APP_ID,
            app_secret=settings.FEISHU_APP_SECRET,
            heartbeat_interval=settings.FEISHU_LONGCONN_HEARTBEAT_INTERVAL,
            reconnect_interval=settings.FEISHU_LONGCONN_RECONNECT_INTERVAL,
            max_reconnect_attempts=settings.FEISHU_LONGCONN_MAX_RECONNECT_ATTEMPTS,
        )

        # 注册事件处理器
        from app.integrations.feishu.callback import handle_card_action, handle_message_receive

        async def card_action_handler(data: Dict[str, Any]):
            """处理卡片按钮点击事件"""
            event = data.get("event", {})
            action = event.get("action", {})
            action_value = action.get("value", {})

            # 支持字符串类型的 value（需要解析 JSON）
            if isinstance(action_value, str):
                try:
                    action_value = json.loads(action_value)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON in action value: {action_value}")
                    action_value = {}

            user_id = event.get("operator", {}).get("open_id", "unknown")

            await handle_card_action(action_value, user_id)

        async def message_handler(data: Dict[str, Any]):
            """处理接收到的消息"""
            event = data.get("event", {})
            message = event.get("message", {})
            await handle_message_receive(message)

        # 注册处理器
        _longconn_manager.register_handler("card.action.trigger", card_action_handler)
        _longconn_manager.register_handler("im.message.receive_v1", message_handler)

        # 启动连接（会一直运行直到被关闭）
        await _longconn_manager.connect()

    except Exception as e:
        logger.exception(f"Error in long connection: {e}")


async def stop_longconn():
    """
    停止飞书 WebSocket 长连接。
    """
    global _longconn_manager

    if _longconn_manager:
        logger.info("Stopping Feishu long connection...")
        await _longconn_manager.close()
        _longconn_manager = None


def get_longconn_manager() -> Optional[FeishuLongConnManager]:
    """
    获取全局长连接管理器实例。

    返回：
        FeishuLongConnManager 实例，如果未启动则返回 None
    """
    return _longconn_manager
