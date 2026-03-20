#!/usr/bin/env python3
"""
飞书长连接客户端（基于官方 SDK）

根据飞书官方文档实现：
https://open.feishu.cn/document/server-docs/event-subscription-guide/event-subscription-configure-/request-url-configuration-case
"""

import asyncio
from threading import Thread
from typing import Optional

import lark_oapi as lark

from app.integrations.feishu.callback import handle_card_action, handle_message_receive
from app.utils.logger import get_logger

logger = get_logger(__name__)


class FeishuLongConnClient:
    """
    飞书长连接客户端（官方 SDK）

    功能优势：
    1. 无需公网 IP 或域名
    2. 无需内网穿透工具
    3. 加密传输，无需额外处理加密解密逻辑
    4. 开发调试方便快捷

    注意事项：
    1. 仅支持企业自建应用
    2. 需要在 3 秒内处理完成事件
    3. 每个应用最多 50 个连接
    4. 集群模式，不支持广播
    """

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.ws_client: Optional[lark.ws.Client] = None
        self.thread: Optional[Thread] = None
        self.event_handler = None
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None  # FastAPI 主 loop

        logger.info(f"FeishuLongConnClient 初始化: app_id={app_id[:10]}...")

    def _create_event_handler(self) -> lark.EventDispatcherHandler:
        """
        创建事件处理器

        注意：
        - builder() 的两个参数必须填空字符串
        - v2.0 事件使用 register_p2_* 方法

        Returns:
            事件处理器实例
        """

        # v2.0 事件处理器
        def handle_im_message_receive_v1(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
            """处理接收消息事件（v2.0）"""
            try:
                # 获取消息内容和发送者
                message = data.event.message
                sender = data.event.sender

                # 提取关键信息
                message_type = message.message_type  # text, image, post 等
                message_id = message.message_id
                chat_id = message.chat_id
                content = message.content  # JSON 字符串

                # 解析消息内容
                import json

                try:
                    content_obj = json.loads(content) if content else {}

                    # 根据消息类型提取文本
                    if message_type == "text":
                        text = content_obj.get("text", "")
                        logger.info(f"📩 收到文本消息:")
                        logger.info(
                            f"  发送者: {sender.sender_id.user_id if sender.sender_id else 'Unknown'}"
                        )
                        logger.info(f"  消息内容: {text}")
                        logger.info(f"  会话ID: {chat_id}")
                        logger.info(f"  消息ID: {message_id}")
                    elif message_type == "post":
                        # 富文本消息
                        logger.info(f"📝 收到富文本消息:")
                        logger.info(
                            f"  发送者: {sender.sender_id.user_id if sender.sender_id else 'Unknown'}"
                        )
                        logger.info(
                            f"  内容: {json.dumps(content_obj, ensure_ascii=False, indent=2)}"
                        )
                    else:
                        logger.info(f"📬 收到 {message_type} 类型消息:")
                        logger.info(
                            f"  发送者: {sender.sender_id.user_id if sender.sender_id else 'Unknown'}"
                        )
                        logger.info(f"  原始内容: {content}")

                except json.JSONDecodeError:
                    logger.warning(f"⚠️  消息内容解析失败: {content}")

                # 打印完整的消息数据（调试用）
                logger.debug(f"完整消息数据: {lark.JSON.marshal(data, indent=4)}")

                # 异步处理（必须在3秒内返回）
                # 注意：不要在这里做耗时操作！
                self._async_handle_message(message, sender)

            except Exception as e:
                logger.exception(f"处理消息事件失败: {e}")

        # 构建事件处理器
        # 注意：builder() 的两个参数必须是空字符串
        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(handle_im_message_receive_v1)
            .build()
        )

        logger.info("事件处理器已创建")
        return event_handler

    def _async_handle_message(self, message, sender):
        """把消息处理提交到 FastAPI 主线程的 event loop（线程安全）"""
        message_dict = {
            "message_id": message.message_id,
            "message_type": message.message_type,
            "chat_id": message.chat_id,
            "content": message.content,
            "sender": {
                "sender_id": {
                    "user_id": (
                        sender.sender_id.user_id if sender and sender.sender_id else "unknown"
                    )
                }
            },
        }
        logger.info(
            f"📤 提交消息处理任务: chat_id={message_dict['chat_id']}, type={message_dict['message_type']}"
        )

        if self._main_loop is None or self._main_loop.is_closed():
            logger.error("❌ 主 event loop 不可用，消息处理失败")
            return

        future = asyncio.run_coroutine_threadsafe(
            handle_message_receive(message_dict),
            self._main_loop,
        )
        future.add_done_callback(
            lambda f: (
                logger.error(f"❌ 消息处理异常: {f.exception()}")
                if f.exception()
                else logger.info("✅ 消息处理完成")
            )
        )

    def _async_handle_card_action(self, action, operator):
        """异步处理卡片动作"""
        try:
            asyncio.run(handle_card_action(action, operator))

        except Exception as e:
            logger.error(f"异步处理卡片动作失败: {e}")

    def start(self, main_loop: Optional[asyncio.AbstractEventLoop] = None):
        """
        启动长连接客户端（在独立线程中运行）

        Args:
            main_loop: FastAPI 主线程的 event loop，用于线程安全地提交异步任务
        """
        if self.thread and self.thread.is_alive():
            logger.warning("长连接客户端已在运行中")
            return

        self._main_loop = main_loop or asyncio.get_event_loop()
        logger.info(f"正在启动飞书长连接客户端，主 loop: {self._main_loop}")

        def run_ws_client():
            """在独立线程中运行 WebSocket 客户端"""
            # 为这个线程创建完全独立的事件循环
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)

            # HACK: 替换 SDK 的全局 loop 变量
            import lark_oapi.ws.client as ws_client_module

            ws_client_module.loop = new_loop

            try:
                # 创建事件处理器
                self.event_handler = self._create_event_handler()

                # 创建 WebSocket 客户端
                self.ws_client = lark.ws.Client(
                    app_id=self.app_id,
                    app_secret=self.app_secret,
                    event_handler=self.event_handler,
                    log_level=lark.LogLevel.INFO,
                )

                logger.info("飞书长连接客户端已创建，正在连接...")

                # 启动连接（会阻塞当前线程）
                self.ws_client.start()

            except Exception as e:
                logger.exception(f"飞书长连接启动失败: {e}")
            finally:
                new_loop.close()

        # 在新线程中启动
        self.thread = Thread(target=run_ws_client, daemon=True, name="FeishuLongConnThread")
        self.thread.start()

        logger.info("✅ 飞书长连接线程已启动")

    def stop(self):
        """停止长连接客户端"""
        if self.ws_client:
            try:
                logger.info("正在停止飞书长连接...")
                # SDK 的 stop 方法（如果有）
                # self.ws_client.stop()
            except Exception as e:
                logger.error(f"停止长连接失败: {e}")

        if self.thread:
            self.thread.join(timeout=5)

        logger.info("飞书长连接已停止")

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.thread is not None and self.thread.is_alive()


# 全局实例
_feishu_longconn_client: Optional[FeishuLongConnClient] = None


def get_feishu_longconn_client() -> Optional[FeishuLongConnClient]:
    """获取全局长连接客户端实例"""
    return _feishu_longconn_client


def init_feishu_longconn_client(app_id: str, app_secret: str) -> FeishuLongConnClient:
    """
    初始化全局长连接客户端

    Args:
        app_id: 飞书应用 ID
        app_secret: 飞书应用密钥

    Returns:
        长连接客户端实例
    """
    global _feishu_longconn_client
    _feishu_longconn_client = FeishuLongConnClient(app_id, app_secret)
    return _feishu_longconn_client


def start_feishu_longconn(
    app_id: str,
    app_secret: str,
    main_loop: Optional[asyncio.AbstractEventLoop] = None,
):
    """快速启动飞书长连接"""
    client = init_feishu_longconn_client(app_id, app_secret)
    client.start(main_loop=main_loop)
    return client


# 使用示例
if __name__ == "__main__":
    # 测试长连接
    import os

    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")

    if not app_id or not app_secret:
        print("请设置环境变量: FEISHU_APP_ID, FEISHU_APP_SECRET")
        exit(1)

    client = start_feishu_longconn(app_id, app_secret)

    # 主线程阻塞，等待事件
    try:
        while True:
            import time

            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止...")
        client.stop()
