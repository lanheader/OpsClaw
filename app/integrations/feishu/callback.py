"""飞书消息处理 - 新架构版本"""

import asyncio
import base64
import hashlib
import json
import re
import traceback
from typing import Any, Dict, Literal, Optional

from Crypto.Cipher import AES
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Overwrite

from app.core.checkpointer import get_checkpointer
from app.core.llm_factory import LLMFactory
from app.core.permission_checker import get_user_permission_codes
from app.core.state import OpsState
from app.deepagents.factory import create_agent_for_session
from app.deepagents.main_agent import get_thread_config
from app.integrations.feishu.callback_extensions import (
    handle_end_session_command,
    handle_new_session_command,
)
from app.integrations.feishu.client import get_feishu_client
from app.integrations.feishu.message_formatter import (
    clean_xml_tags,
    format_clarification_request,
    format_error_message,
    format_help_message,
    format_insufficient_confidence,
    format_pending_approval_warning,
)
from app.models.chat_message import MessageRole
from app.models.database import SessionLocal
from app.models.user import User
from app.services.approval_intent_service import classify_approval_intent
from app.services.chat_service import get_or_create_feishu_session, save_feishu_message
from app.services.session_state_manager import SessionStateManager
from app.utils.llm_helper import ensure_final_report_in_state
from app.utils.logger import get_logger, set_request_context, clear_request_context
from app.deepagents.main_agent import get_ops_agent_enhanced

logger = get_logger(__name__)


def _convert_card_to_readable_text(card: Dict[str, Any]) -> str:
    """
    将飞书卡片转换为可读的文本格式，用于保存到数据库和 Web 显示

    Args:
        card: 飞书卡片 JSON

    Returns:
        可读的文本格式
    """
    lines = []

    # 提取标题
    header = card.get("header", {})
    title_obj = header.get("title", {})
    title = title_obj.get("content", "")
    if title:
        lines.append(f"## {title}\n")

    # 提取元素内容
    # 飞书卡片结构：card.body.elements 或 card.elements（兼容两种格式）
    body = card.get("body", {})
    elements = body.get("elements", []) if body else card.get("elements", [])

    for element in elements:
        tag = element.get("tag")

        # 分隔线
        if tag == "hr":
            lines.append("---")

        # 文本内容
        elif tag == "div":
            text_obj = element.get("text", {})
            text_tag = text_obj.get("tag")
            content = text_obj.get("content", "")

            if text_tag == "lark_md":
                # Markdown 内容
                lines.append(content)
            elif text_tag == "plain_text":
                # 纯文本
                lines.append(content)

        # Markdown 内容（飞书卡片 body.elements 中的 markdown tag）
        elif tag == "markdown":
            content = element.get("content", "")
            if content:
                lines.append(content)

        # 列（用于表格布局）
        elif tag == "column_set":
            columns = element.get("columns", [])
            column_texts = []
            for col in columns:
                col_elements = col.get("elements", [])
                for col_el in col_elements:
                    if col_el.get("tag") == "div":
                        text_obj = col_el.get("text", {})
                        content = text_obj.get("content", "")
                        if content:
                            # 移除 markdown 加粗标记以保持表格简洁
                            content = content.replace("**", "")
                            column_texts.append(content)
            if column_texts:
                lines.append(" | ".join(column_texts))

        # 交互按钮
        elif tag == "action":
            actions = element.get("actions", [])
            button_texts = []
            for action in actions:
                if action.get("tag") == "button":
                    text_obj = action.get("text", {})
                    button_text = text_obj.get("content", "")
                    if button_text:
                        button_texts.append(f"[{button_text}]")
            if button_texts:
                lines.append(f"\n操作: {' '.join(button_texts)}")

    # 组合内容，清理多余的空行
    result = "\n".join(lines)
    # 替换连续的多个换行为最多两个
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()


# 确认关键词
CONFIRMATION_KEYWORDS = {
    "好的",
    "可以",
    "同意",
    "批准",
    "确认",
    "ok",
    "yes",
    "是的",
    "行",
    "嗯",
}

# 飞书消息最大长度
MAX_FEISHU_MESSAGE_LENGTH = 3500
INTERRUPT_PLACEHOLDER_MESSAGE = (
    "⏸️ 操作需要您的批准，但批准流程尚未完全实现。\n\n" "当前版本暂时禁用了批准流程，请稍后重试。"
)
NO_PENDING_APPROVAL_MESSAGE = (
    "当前没有待确认的操作。\n\n"
    "像“查看 Pod 列表”“查询集群状态”这类只读查询，我会直接执行，不需要你再回复“同意”。\n\n"
    "只有删除、重启、变更配置这类操作，才会单独请求确认。\n\n"
    "如果你想继续，可以直接告诉我新的需求，例如：\n"
    '- "查看 Pod 列表"\n'
    '- "只看异常 Pod"\n'
    '- "诊断服务问题"\n'
)


def unwrap_overwrite(obj: Any) -> Any:
    """递归解包 LangGraph 的 Overwrite 对象。"""
    while isinstance(obj, Overwrite):
        obj = obj.value
    return obj


async def format_tool_output(content: str) -> dict:
    """格式化输出为飞书卡片格式。"""
    # 清理 XML 标签
    content = clean_xml_tags(content)

    title = "💬 回复"
    for line in content.split("\n"):
        if line.startswith("##"):
            title = line.replace("##", "").strip()
            break
        if line.startswith("#"):
            title = line.replace("#", "").strip()
            break

    if len(title) > 50:
        title = title[:47] + "..."

    # 检测 Markdown 表格并包裹在代码块中（飞书不支持表格语法）
    # 但要避免重复添加代码块标记
    if "|" in content and "---" in content:
        # 检查是否已经包含代码块标记
        if "```" not in content:
            pass

    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "blue",
            },
            "body": {
                "elements": [
                    {
                        "tag": "markdown",
                        "content": content,
                    }
                ]
            },
        },
    }


def should_skip_message(content: str) -> bool:
    """
    判断是否应该跳过这条消息（不发送给用户）。

    注意：此功能已禁用，所有消息都会发送给用户。
    """
    # 始终返回 False，不跳过任何消息
    return False


def _log_diagnostic_info(
    diag_collector: Dict[str, Any],
    session_id: str,
    chat_id: str,
    event_count: int,
) -> None:
    """
    输出诊断信息，帮助分析为什么没有生成回复。

    使用流处理期间收集的信息，而不是从 checkpointer 重新获取。
    """
    logger.error(f"")
    logger.error(f"{'='*60}")
    logger.error(f"❌ [诊断] 工作流执行完成但没有生成任何回复！")
    logger.error(f"{'='*60}")
    logger.error(f"")
    logger.error(f"📊 基本信息:")
    logger.error(f"   - session_id: {session_id}")
    logger.error(f"   - chat_id: {chat_id}")
    logger.error(f"   - 事件数量: {event_count}")
    logger.error(f"")

    # 分析事件类型
    event_types = {}
    for event in diag_collector.get("events", []):
        etype = str(event.get("type", "unknown"))
        event_types[etype] = event_types.get(etype, 0) + 1

    logger.error(f"📍 事件类型分布:")
    if event_types:
        for etype, count in sorted(event_types.items()):
            logger.error(f"   - {etype}: {count} 次")
    else:
        logger.error(f"   (无事件记录)")
    logger.error(f"")

    # 分析消息
    messages_seen = diag_collector.get("messages_seen", [])
    logger.error(f"📨 消息处理情况:")
    logger.error(f"   - 处理消息数: {len(messages_seen)}")

    msg_types = {}
    for msg in messages_seen:
        mtype = msg.get("type", "unknown")
        msg_types[mtype] = msg_types.get(mtype, 0) + 1

    if msg_types:
        logger.error(f"   - 消息类型分布:")
        for mtype, count in sorted(msg_types.items()):
            logger.error(f"     * {mtype}: {count} 条")
    else:
        logger.error(f"   (无消息处理记录)")

    # 分析 AI 回复
    ai_replies = diag_collector.get("ai_replies", [])
    logger.error(f"")
    logger.error(f"🤖 AI 回复情况:")
    logger.error(f"   - AI 回复数: {len(ai_replies)}")

    if ai_replies:
        for i, reply in enumerate(ai_replies, 1):
            logger.error(f"   回复 #{i} [索引{reply['index']}]:")
            logger.error(f"     - 内容长度: {reply['content_length']} 字符")
            logger.error(f"     - 内容预览: {reply['content_preview'][:100]}...")
    else:
        logger.error(f"   (无 AI 回复记录)")
        logger.error(f"")
        logger.error(f"   ⚠️ 可能原因:")
        logger.error(f"   1. LLM 返回了空内容")
        logger.error(f"   2. AI 回复被 should_skip_message 过滤")
        logger.error(f"   3. 只有工具调用，没有最终回复")

    # 分析工具调用
    tool_calls = diag_collector.get("tool_calls", [])
    logger.error(f"")
    logger.error(f"🔧 工具调用情况:")
    logger.error(f"   - 工具调用数: {len(tool_calls)}")

    if tool_calls:
        # 统计每个工具的调用次数
        tool_counts = {}
        for tool in tool_calls:
            tool_counts[tool] = tool_counts.get(tool, 0) + 1

        logger.error(f"   - 调用工具列表:")
        for tool, count in sorted(tool_counts.items()):
            logger.error(f"     * {tool}: {count} 次")
    else:
        logger.error(f"   (无工具调用记录)")

    # 分析后备回复
    fallback_replies = diag_collector.get("fallback_replies", [])
    logger.error(f"")
    logger.error(f"💾 后备回复情况:")
    logger.error(f"   - 后备回复数: {len(fallback_replies)}")

    if fallback_replies:
        for i, fallback in enumerate(fallback_replies, 1):
            logger.error(f"   后备回复 #{i}: {len(fallback)} 字符")
            logger.error(f"     预览: {fallback[:150]}...")
    else:
        logger.error(f"   (无后备回复)")

    # 分析最终状态
    final_state = diag_collector.get("final_state")
    logger.error(f"")
    logger.error(f"🏁 最终状态:")

    if final_state:
        logger.error(f"   - 状态类型: {type(final_state)}")

        # 打印关键状态字段
        important_keys = [
            "workflow_status", "intent_type", "data_sufficient",
            "root_cause", "severity", "execution_success", "final_report"
        ]

        for key in important_keys:
            value = final_state.get(key, "(未设置)")
            if value and value != "(未设置)":
                # 截断过长的值
                value_str = str(value)
                if len(value_str) > 100:
                    value_str = value_str[:100] + "..."
                logger.error(f"   - {key}: {value_str}")

        # 检查 formatted_response
        formatted_response = final_state.get("formatted_response")
        if formatted_response:
            logger.error(f"   - formatted_response: {len(str(formatted_response))} 字符")
        else:
            logger.error(f"   ⚠️ formatted_response 为空")
    else:
        logger.error(f"   (无最终状态记录)")

    logger.error(f"")
    logger.error(f"{'='*60}")
    logger.error(f"")


async def _diagnose_message_state(
    session_id: str,
    chat_id: str,
    initial_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    诊断消息状态，用于分析为什么没有生成回复。

    参数:
        session_id: 会话 ID
        chat_id: 飞书聊天 ID
        initial_state: 初始状态（如果提供，使用运行时状态而非 checkpointer）

    返回消息统计信息，包括：
    - 总消息数
    - 各类型消息数量
    - 被跳过的消息统计
    - 最后处理的索引
    """
    from app.services.session_state_manager import SessionStateManager
    from app.core.checkpointer import get_checkpointer

    stats = {
        "session_id": session_id,
        "chat_id": chat_id,
        "total_messages": 0,
        "last_processed_index": -1,
        "message_types": {},
        "ai_messages": 0,
        "ai_messages_empty": 0,
        "ai_messages_with_tool_calls": 0,
        "human_messages": 0,
        "tool_messages": 0,
        "sample_messages": [],
        "state_source": "checkpointer",
    }

    messages = None

    # 优先使用运行时状态
    if initial_state and "messages" in initial_state:
        messages = unwrap_overwrite(initial_state["messages"])
        stats["state_source"] = "runtime"
        logger.info(f"🔍 [诊断] 使用运行时状态分析消息")
    else:
        # 从 checkpointer 获取状态
        try:
            checkpointer = await get_checkpointer()
            config = {"configurable": {"thread_id": session_id}}
            saved_state = await checkpointer.aget_tuple(config)

            if saved_state:
                # 先尝试从 checkpoint 获取
                if saved_state.checkpoint:
                    state = saved_state.checkpoint
                    messages = state.get("messages", None)
                    if messages:
                        stats["state_source"] = "checkpoint"

                # 如果 checkpoint 中没有，尝试从 channel_values 获取
                if not messages and hasattr(saved_state, 'channel_values'):
                    cv = saved_state.channel_values
                    if cv and "messages" in cv:
                        messages = cv.get("messages", None)
                        if messages:
                            stats["state_source"] = "channel_values"
                            logger.info(f"🔍 [诊断] 从 channel_values 获取消息")

                if not messages:
                    stats["warning"] = "checkpointer 存在但没有 messages 字段"
                    logger.error(f"🔍 [诊断] checkpointer 结构: checkpoint={type(saved_state.checkpoint)}, channel_values={type(getattr(saved_state, 'channel_values', None))}")
                    if saved_state.checkpoint:
                        logger.error(f"🔍 [诊断] checkpoint keys: {list(saved_state.checkpoint.keys()) if isinstance(saved_state.checkpoint, dict) else 'not a dict'}")
        except Exception as e:
            logger.warning(f"⚠️ [诊断] 获取 checkpointer 状态失败: {e}")
            stats["error"] = f"获取状态失败: {e}"

    if not messages:
        stats["warning"] = f"消息为空: source={stats.get('state_source', 'unknown')}, type={type(messages)}"
        return stats

    if not isinstance(messages, list):
        stats["warning"] = f"消息不是列表: type={type(messages)}"
        return stats

    stats["total_messages"] = len(messages)
    last_processed = SessionStateManager.get_last_processed_message_index(session_id)
    stats["last_processed_index"] = last_processed or -1

    # 分析消息类型
    for idx, msg in enumerate(messages):
        msg_type = type(msg).__name__
        stats["message_types"][msg_type] = stats["message_types"].get(msg_type, 0) + 1

        if isinstance(msg, AIMessage):
            stats["ai_messages"] += 1
            content = getattr(msg, "content", None)
            tool_calls = getattr(msg, "tool_calls", None)

            if tool_calls and len(tool_calls) > 0:
                stats["ai_messages_with_tool_calls"] += 1
            if not content:
                stats["ai_messages_empty"] += 1

            # 记录最近 5 条 AI 消息的样本
            if stats["ai_messages"] <= 5:
                content_str = str(content) if content else ""
                stats["sample_messages"].append({
                    "index": idx,
                    "type": msg_type,
                    "has_content": bool(content),
                    "content_length": len(content_str),
                    "content_preview": content_str[:100],
                    "has_tool_calls": bool(tool_calls),
                    "tool_calls_count": len(tool_calls) if tool_calls else 0,
                    "would_skip": should_skip_message(content_str) if content_str else False,
                })

        elif isinstance(msg, HumanMessage):
            stats["human_messages"] += 1
        elif isinstance(msg, ToolMessage):
            stats["tool_messages"] += 1

    return stats


def verify_webhook_signature(
    timestamp: str,
    nonce: str,
    encrypt_key: str,
    body: str,
    signature: str,
) -> bool:
    """验证飞书 Webhook 请求签名。"""
    try:
        string_to_sign = f"{timestamp}{nonce}{encrypt_key}{body}"
        calculated_signature = hashlib.sha256(string_to_sign.encode()).hexdigest()
        return calculated_signature == signature
    except Exception as exc:
        logger.exception(f"Error verifying signature: {exc}")
        return False


def decrypt_message(encrypt_key: str, encrypted_data: str) -> str:
    """解密飞书加密消息。"""
    try:
        key = encrypt_key.encode("utf-8")
        if len(key) > 32:
            key = key[:32]
        elif len(key) < 32:
            key = key.ljust(32, b"\0")

        cipher = AES.new(key, AES.MODE_CBC, key[:16])
        encrypted_bytes = base64.b64decode(encrypted_data)
        decrypted = cipher.decrypt(encrypted_bytes)

        padding_len = decrypted[-1]
        decrypted = decrypted[:-padding_len]
        return decrypted.decode("utf-8")
    except ImportError:
        logger.error("pycryptodome not installed")
        raise RuntimeError("pycryptodome is required for message decryption")
    except Exception as exc:
        logger.exception(f"Error decrypting message: {exc}")
        raise


async def handle_message_receive(message: Dict[str, Any]) -> None:
    """处理接收到的消息事件 - 新架构版本。"""
    try:
        await _handle_message_receive_impl(message)
    except NotImplementedError as exc:
        _print_critical_error("NotImplementedError", exc)
        await _try_send_not_implemented_error(message)
        raise
    except Exception as exc:
        _print_critical_error(type(exc).__name__, exc)
        raise


async def _handle_message_receive_impl(message: Dict[str, Any]) -> None:
    """处理接收到的消息事件 - 实现。"""
    chat_id: Optional[str] = None
    session_id: Optional[str] = None

    try:
        _log_received_message(message)

        message_id = message.get("message_id")
        message_type = message.get("message_type")
        chat_id = message.get("chat_id")
        sender_id = message.get("sender", {}).get("sender_id", {}).get("user_id", "unknown")
        raw_content = message.get("content", {})

        # 设置请求上下文（用于日志追踪）- 使用 chat_id 作为临时 session_id
        set_request_context(
            session_id=chat_id or "unknown",
            user_id=sender_id,
            channel="feishu"
        )
        logger.info(f"📥 收到飞书消息: sender={sender_id}, chat_id={chat_id}")

        await _try_add_message_reaction(message_id)

        if message_type != "text":
            logger.debug(f"Unsupported message type: {message_type}")
            return

        text = _extract_message_text(raw_content)
        if not text:
            logger.warning("Empty message text after cleaning")
            return

        # 验证用户是否绑定了飞书ID
        if not await _verify_feishu_user_binding(sender_id, chat_id):
            return

        sender_name = await _fetch_sender_name(sender_id)
        session_id = await _persist_user_message(chat_id, sender_id, sender_name, text)

        # 更新请求上下文中的 session_id（现在有了真正的 session_id）
        if session_id:
            set_request_context(
                session_id=session_id,
                user_id=sender_id,
                channel="feishu"
            )
            logger.info(f"🔄 已更新 session_id: {session_id}")

        if await _handle_special_command(text, chat_id, sender_id, sender_name, session_id):
            return

        logger.info(f"🚀 调用新工作流引擎处理消息: {text}")
        session_id = session_id or await _load_session_id(chat_id, sender_id, sender_name)

        approval_handled = await _try_handle_pending_approval(
            session_id=session_id,
            chat_id=chat_id,
            text=text,
        )
        if approval_handled:
            return

        if _is_confirmation_only(text):
            logger.warning(f"⚠️ 用户回复了确认词，但没有待批准的工作流: {text}")
            await _send_text_reply(chat_id, NO_PENDING_APPROVAL_MESSAGE)
            return

        await _process_normal_workflow(
            chat_id=chat_id, session_id=session_id, text=text, sender_id=sender_id
        )
    except Exception as exc:
        logger.exception(f"❌ 处理飞书消息失败: {exc}")
        print(f"❌ [feishu_callback] Error handling message: {exc}")
        traceback.print_exc()
        try:
            detailed_error = (
                "❌ 出了点问题\n\n"
                f"**错误类型**: {type(exc).__name__}\n"
                f"**错误信息**: {str(exc)}\n\n"
                "如果问题持续，请联系技术支持。"
            )
            await _send_text_reply(chat_id, detailed_error)
        except Exception:
            pass
    finally:
        # 清除请求上下文
        clear_request_context()
        logger.info("📤 飞书消息处理完成，已清除请求上下文")


async def _try_send_not_implemented_error(message: Dict[str, Any]) -> None:
    """尽力向用户发送 NotImplementedError 调试信息。"""
    chat_id = message.get("chat_id")
    if not chat_id:
        return

    try:
        client = get_feishu_client()
        await client.send_text_message(
            chat_id,
            f"❌ NotImplementedError\n\n```\n{traceback.format_exc()}\n```",
        )
    except Exception:
        pass


def _print_critical_error(error_type: str, exc: Exception) -> None:
    """输出关键错误到控制台。"""
    print(f"❌❌❌ [CRITICAL] {error_type} in handle_message_receive: {exc}")
    traceback.print_exc()


def _log_received_message(message: Dict[str, Any]) -> None:
    """记录收到的飞书消息。"""
    logger.info("=" * 60)
    logger.info("🎯 飞书消息回调被触发 (DeepAgents 架构)")
    logger.info(f"📨 消息内容: {message}")
    logger.info("=" * 60)


async def _try_add_message_reaction(message_id: Optional[str]) -> None:
    """尽力给飞书消息加上 OK 表情。"""
    if not message_id:
        return

    try:
        client = get_feishu_client()
        await client.add_message_reaction(message_id, emoji_type="OK")
        logger.info(f"✅ 已为消息 {message_id} 添加 OK 表情")
    except Exception as exc:
        logger.warning(f"⚠️ 添加表情回复失败: {exc}")


async def _verify_feishu_user_binding(sender_id: str, chat_id: str) -> bool:
    """验证飞书用户是否已绑定系统账号。

    Args:
        sender_id: 飞书用户ID
        chat_id: 飞书会话ID

    Returns:
        bool: True 表示已绑定，False 表示未绑定
    """
    try:
        db = SessionLocal()
        try:
            # 查询是否存在绑定了该飞书ID的用户
            user = db.query(User).filter(User.feishu_user_id == sender_id).first()

            if not user:
                logger.warning(f"⚠️ 飞书用户 {sender_id} 未绑定系统账号")
                # 发送提示消息
                unbind_message = (
                    "❌ 您还未绑定系统账号\n\n"
                    "请先在 Web 管理后台绑定您的飞书账号，才能使用飞书聊天功能。\n\n"
                    "绑定步骤：\n"
                    "1. 登录 Web 管理后台\n"
                    "2. 进入「个人设置」\n"
                    "3. 点击「绑定飞书账号」\n"
                    "4. 完成绑定后即可使用\n\n"
                    "如有疑问，请联系管理员。"
                )
                await _send_text_reply(chat_id, unbind_message)
                return False

            if not user.is_active:
                logger.warning(f"⚠️ 用户 {user.username} (飞书ID: {sender_id}) 账号已被禁用")
                disabled_message = "❌ 您的账号已被禁用\n\n" "如有疑问，请联系管理员。"
                await _send_text_reply(chat_id, disabled_message)
                return False

            logger.info(f"✅ 飞书用户 {sender_id} 已绑定到系统用户 {user.username}")
            return True

        finally:
            db.close()

    except Exception as exc:
        logger.exception(f"❌ 验证飞书用户绑定失败: {exc}")
        error_message = "❌ 系统错误\n\n" "验证用户绑定时出现错误，请稍后重试或联系管理员。"
        await _send_text_reply(chat_id, error_message)
        return False


def _extract_message_text(content: Any) -> str:
    """解析并清洗飞书文本消息。"""
    parsed_content = content
    if isinstance(parsed_content, str):
        try:
            parsed_content = json.loads(parsed_content)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse content as JSON: {content}")
            return ""

    text = parsed_content.get("text", "") if isinstance(parsed_content, dict) else ""
    logger.info(f"📩 Message text: {text}")
    return text.replace("@_user_1", "").replace("@Ops Agent", "").strip()


def _extract_sent_message_ids(response: Dict[str, Any]) -> list[str]:
    """从飞书 API 响应中提取发送的消息 ID 列表。"""
    message_ids: list[str] = []
    if not isinstance(response, dict):
        return message_ids

    # 检查响应是否成功
    if response.get("code") != 0:
        logger.warning(f"飞书 API 响应错误: {response.get('msg')}")
        return message_ids

    # 提取 message_id
    data = response.get("data", {})
    if isinstance(data, dict):
        message_id = data.get("message_id")
        if message_id:
            message_ids.append(message_id)

    return message_ids


async def _fetch_sender_name(sender_id: str) -> Optional[str]:
    """获取飞书用户名称。"""
    try:
        client = get_feishu_client()
        user_info = await client.get_user_info(sender_id)
        if user_info:
            sender_name = user_info.get("name") or user_info.get("en_name")
            logger.info(f"📝 Got Feishu user name: {sender_name}")
            return sender_name
    except Exception as exc:
        logger.warning(f"⚠️ Failed to get Feishu user info: {exc}")
    return None


async def _persist_user_message(
    chat_id: str,
    sender_id: str,
    sender_name: Optional[str],
    text: str,
) -> Optional[str]:
    """获取会话并保存用户消息。"""
    db = SessionLocal()
    try:
        session = await get_or_create_feishu_session(db, chat_id, sender_id, sender_name)
        save_feishu_message(db, session.session_id, MessageRole.USER, text)
        logger.info("✅ 已保存飞书用户消息到数据库")
        return session.session_id
    except Exception as exc:
        logger.error(f"❌ 保存飞书消息失败: {exc}")
        return None
    finally:
        db.close()


async def _load_session_id(
    chat_id: str,
    sender_id: str,
    sender_name: Optional[str],
) -> Optional[str]:
    """重新获取会话 ID。"""
    db = SessionLocal()
    try:
        session = await get_or_create_feishu_session(db, chat_id, sender_id, sender_name)
        return session.session_id
    except Exception as exc:
        logger.error(f"❌ 获取会话失败: {exc}")
        return None
    finally:
        db.close()


async def _handle_special_command(
    text: str,
    chat_id: str,
    sender_id: str,
    sender_name: Optional[str],
    session_id: Optional[str],
) -> bool:
    """处理特殊命令，已处理则返回 True。"""
    if text.startswith("/help"):
        await _send_help_message(chat_id)
        return True

    if text.startswith("/new"):
        await handle_new_session_command(chat_id, sender_id, sender_name, _send_text_reply)
        return True

    if text.startswith("/end"):
        await handle_end_session_command(chat_id, session_id, _send_text_reply)
        return True

    return False


async def _try_handle_pending_approval(
    session_id: Optional[str],
    chat_id: str,
    text: str,
) -> bool:
    """如果当前会话有待审批状态，则处理审批分支。"""

    approval_data = SessionStateManager.check_awaiting_approval(session_id)
    if not approval_data:
        return False

    logger.info(f"✅ 检测到会话 {session_id} 处于等待批准状态")
    logger.info(f"📋 批准数据: {approval_data}")

    try:
        # 使用默认 LLM provider（不再使用 profile）
        llm = LLMFactory.create_llm()
        intent_result = await classify_approval_intent(
            user_input=text,
            llm=llm,
            approval_context=approval_data,
        )

        intent_type = intent_result.get("intent_type")
        confidence = intent_result.get("confidence", 0)
        reasoning = intent_result.get("reasoning", "")
        logger.info(f"🎯 意图识别结果: {intent_type}, 置信度: {confidence}, 理由: {reasoning}")

        if intent_type == "approval" and confidence >= 0.7:
            await _resume_approval_flow(session_id, "approved", chat_id, text)
            return True

        if intent_type == "rejection" and confidence >= 0.7:
            await _resume_approval_flow(session_id, "rejected", chat_id, text)
            return True

        if intent_type == "clarification":
            logger.info("❓ 用户请求澄清")
            clarification_msg = format_clarification_request(
                commands_summary=approval_data.get("commands_summary", "未知操作"),
                risk_level=approval_data.get("risk_level", "未知"),
            )
            await _send_text_reply(chat_id, clarification_msg)
            return True

        if confidence < 0.7:
            logger.warning(f"⚠️ 意图识别置信度不足: {confidence}")
            await _send_text_reply(
                chat_id,
                format_insufficient_confidence(confidence, approval_data),
            )
            return True

        logger.info("🔄 用户提出了新请求，但当前有待批准的操作")
        await _send_text_reply(chat_id, format_pending_approval_warning(approval_data))
        return True
    except Exception as exc:
        logger.error(f"❌ 处理批准响应失败: {exc}", exc_info=True)
        await _send_text_reply(chat_id, format_error_message(exc))
        SessionStateManager.reset_to_normal(session_id)
        return True


async def _resume_approval_flow(
    session_id: str,
    decision: str,
    chat_id: str,
    user_response: str,
) -> None:
    """恢复批准流程并在必要时重置会话状态。"""
    logger.info(f"{'✅' if decision == 'approved' else '❌'} 用户{decision}执行操作")
    SessionStateManager.set_processing(session_id)

    resume_status: Optional[str] = None
    try:
        resume_status = await _handle_approval_response(
            session_id=session_id,
            decision=decision,
            chat_id=chat_id,
            user_response=user_response,
        )
    except Exception as exc:
        logger.error(f"❌ 恢复工作流失败: {exc}", exc_info=True)
        raise
    finally:
        if resume_status == "completed":
            SessionStateManager.reset_to_normal(session_id)


def _is_confirmation_only(text: str) -> bool:
    """判断消息是否是无上下文的简短确认词。"""
    return text.lower() in CONFIRMATION_KEYWORDS or len(text) <= 3


async def _process_normal_workflow(
    chat_id: str, session_id: str, text: str, sender_id: str
) -> None:
    """处理普通查询/执行类工作流。"""
    logger.info(f"📝 会话 {session_id} 处于正常状态，开始执行工作流")

    # 注意：不再需要手动加载历史消息
    # LangGraph 的 SQLite checkpointer 会自动通过 thread_id 恢复会话状态
    logger.info(f"📚 使用 LangGraph checkpointer 自动恢复会话状态（thread_id={session_id}）")

    try:
        # 获取用户权限
        user_permissions = None
        db = SessionLocal()
        try:
            # 从飞书用户ID获取系统用户
            user = db.query(User).filter(User.feishu_user_id == sender_id).first()

            if user:
                # 获取用户权限代码
                permission_codes = get_user_permission_codes(db, user.id)
                user_permissions = set(permission_codes)
                logger.info(
                    f"🔐 用户 {user.username} 的权限: {', '.join(sorted(user_permissions)) if user_permissions else '无'}"
                )
            else:
                logger.warning(f"⚠️ 未找到绑定飞书ID的用户，使用默认权限")
        finally:
            db.close()

        logger.info("📦 正在获取 Agent...")
        # agent = await create_agent_for_session(
        #     session_id=session_id,
        #     enable_approval=True,
        #     enable_security=True,
        #     user_permissions=user_permissions,
        # )

        agent = await get_ops_agent_enhanced(
            enable_memory=True,
            enable_auto_learn=True,
            user_permissions=user_permissions,
        )

        logger.info(f"✅ Agent 获取成功: {type(agent)}")

        # 【诊断】检查 checkpointer 中的历史状态
        config = get_thread_config(session_id)
        checkpointer = await get_checkpointer()
        try:
            # 尝试加载历史状态
            saved_config = await checkpointer.aget_tuple(config)
            if saved_config:
                # 只显示摘要信息
                cp = saved_config.checkpoint
                if cp and "channel_values" in cp:
                    cv = cp["channel_values"]
                    msg_count = len(cv.get("messages", []))
                    logger.info(f"📚 [Checkpointer] 历史状态: {msg_count} 条消息")
                else:
                    logger.info(f"📚 [Checkpointer] 历史状态: checkpoint={cp.get('ts', '?') if cp else 'None'}")
            else:
                logger.info(f"📚 [Checkpointer] 新会话（无历史状态）")
        except Exception as e:
            logger.warning(f"⚠️ [Checkpointer] 读取历史状态失败: {e}")

        # ========== 构建输入状态 ==========
        # DeepAgents 使用 LangGraph 的 messages channel 来管理对话历史
        # 我们传入当前用户消息，LangGraph 会自动从 checkpoint 加载历史消息
        from langchain_core.messages import HumanMessage

        input_state = {
            "messages": [HumanMessage(content=text)],
        }

        all_replies: list[str] = []
        all_reply_message_ids: list[str] = []

        # 诊断信息收集器
        diag_collector = {
            "events": [],
            "messages_seen": [],
            "ai_replies": [],
            "tool_calls": [],
            "fallback_replies": [],  # 被过滤消息的友好版本
            "final_state": None,
        }

        logger.info(f"🚀 开始流式执行工作流，session_id={session_id}")
        logger.info(f"📝 用户输入: {text[:100]}")
        logger.info(f"⚙️ 配置: {config}")
        logger.info(f"🚀 [feishu_callback] 开始流式执行工作流，session_id={session_id}")

        event_count = 0
        final_state = None  # 捕获最终状态
        async for event in agent.astream(input_state, config=config):
            event_count += 1
            event_type = list(event.keys()) if isinstance(event, dict) else "unknown"

            # 收集诊断信息
            diag_collector["events"].append({
                "index": event_count,
                "type": event_type,
            })

            logger.info(f"📍 事件 #{event_count}: {event_type}")

            # 检查是否是最终状态
            if "__end__" in event:
                logger.info(f"🏁 检测到流结束事件")
                final_state = event.get("__end__", {})
                if diag_collector:
                    diag_collector["final_state"] = final_state
                logger.info(f"📍 [诊断] 最终状态类型: {type(final_state)}, 键: {list(final_state.keys()) if isinstance(final_state, dict) else 'N/A'}")
                logger.info(f"📍 [诊断] 最终状态内容预览: {str(final_state)[:500] if final_state else 'None'}")
                # 处理最终状态中的回复
                await _send_final_state_reply(chat_id, final_state, all_replies, all_reply_message_ids)
                break

            event_result = await _handle_workflow_stream_event(
                event=event,
                chat_id=chat_id,
                session_id=session_id,
                all_replies=all_replies,
                all_reply_message_ids=all_reply_message_ids,
                diag_collector=diag_collector,  # 传递诊断收集器
            )
            if event_result == "interrupted":
                await _persist_assistant_reply(session_id, all_replies, all_reply_message_ids)
                return

        logger.info(f"🏁 工作流执行完成，共 {event_count} 个事件，{len(all_replies)} 条回复")
        logger.info(f"🏁 [feishu_callback] 工作流执行完成，共 {event_count} 个事件")

        # 如果没有回复，尝试使用后备回复
        if not all_replies:
            fallback_replies = diag_collector.get("fallback_replies", [])
            if fallback_replies:
                logger.info(f"💾 [后备回复] 使用 {len(fallback_replies)} 条后备回复")
                for fallback in fallback_replies:
                    all_reply_message_ids.extend(await _send_text_reply(chat_id, fallback) or [])
                    all_replies.append(fallback)
                logger.info(f"✅ [后备回复] 已发送 {len(all_replies)} 条回复")

        # 诊断日志：检查为什么没有回复
        if not all_replies:
            _log_diagnostic_info(diag_collector, session_id, chat_id, event_count)
        else:
            logger.info(f"✅ [诊断] 成功生成 {len(all_replies)} 条回复:")
            for i, reply in enumerate(all_replies, 1):
                logger.info(f"   回复 #{i}: {reply[:100]}...")

        await _persist_assistant_reply(session_id, all_replies, all_reply_message_ids)
    except NotImplementedError as exc:
        logger.error(f"❌ astream NotImplementedError: {exc}")
        traceback.print_exc()
        raise
    except Exception as exc:
        logger.exception(f"❌ 工作流执行失败: {exc}")
        traceback.print_exc()

        error_msg = format_error_message(exc)
        detailed_error = f"{error_msg}\n\n**调试信息**:\n```\n{type(exc).__name__}: {str(exc)}\n```"
        await _send_text_reply(chat_id, detailed_error)
        await _persist_error_reply(session_id, error_msg)


async def _send_final_state_reply(
    chat_id: str,
    final_state: Dict[str, Any],
    all_replies: list[str],
    all_reply_message_ids: list[str],
) -> None:
    """根据 complete 事件中的最终状态发送最终回复。"""
    logger.info(f"📍 [最终状态] final_state 键: {list(final_state.keys()) if isinstance(final_state, dict) else 'N/A'}")

    # 尝试多个可能的键来获取回复
    response_to_send = (
        final_state.get("formatted_response", "") or
        final_state.get("final_report", "") or
        final_state.get("response", "") or
        final_state.get("answer", "") or
        final_state.get("output", "") or
        ""
    )

    # 如果直接键没有找到，尝试从 messages 中获取最后一条 AI 消息
    if not response_to_send and "messages" in final_state:
        messages = final_state.get("messages", [])
        if messages:
            # 从后往前找最后一条有内容的 AIMessage
            for msg in reversed(messages):
                if isinstance(msg, AIMessage):
                    content = getattr(msg, "content", None)
                    if content:
                        response_to_send = content
                        logger.info(f"📍 [最终状态] 从 messages 中提取到回复，长度: {len(response_to_send)}")
                        break

    logger.info(f"📍 [最终状态] 提取的回复长度: {len(response_to_send) if response_to_send else 0}")

    if response_to_send:
        all_reply_message_ids.extend(await _send_text_reply(chat_id, response_to_send) or [])
        all_replies.append(response_to_send)
        logger.info(f"✅ [最终状态] 已发送最终回复，长度: {len(response_to_send)}")
        return

    # 如果还是没有回复，记录详细的 final_state 内容
    logger.warning(f"⚠️ [最终状态] 未找到回复内容")
    logger.warning(f"   final_state 类型: {type(final_state)}")
    logger.warning(f"   final_state 键: {list(final_state.keys()) if isinstance(final_state, dict) else 'N/A'}")
    if isinstance(final_state, dict):
        for key, value in final_state.items():
            value_preview = str(value)[:100] if value not in [None, "", []] else "empty"
            logger.warning(f"   - {key}: {value_preview}")

    status_msg = (
        "✅ **工作流执行完成**\n\n"
        f"意图类型: {final_state.get('intent_type', 'unknown')}\n"
        f"诊断轮次: {final_state.get('diagnosis_round', 0)}\n"
        f"数据充足: {'是' if final_state.get('data_sufficient') else '否'}\n"
    )
    all_reply_message_ids.extend(await _send_text_reply(chat_id, status_msg) or [])
    all_replies.append(status_msg)


async def _handle_workflow_stream_event(
    event: Dict[str, Any],
    chat_id: str,
    session_id: str,
    all_replies: list[str],
    all_reply_message_ids: Optional[list[str]] = None,
    diag_collector: Optional[Dict[str, Any]] = None,
) -> Optional[Literal["completed", "interrupted"]]:
    """处理普通工作流中的单个流事件。"""
    all_reply_message_ids = (
        all_reply_message_ids if all_reply_message_ids is not None else []
    )
    event_type = event.get("type")
    if event_type == "interrupt":
        interrupt_data = event.get("data", {})
        approval_message = interrupt_data.get("message", "")
        logger.info("⏸️ 工作流暂停，需要用户批准")

        all_reply_message_ids.extend(await _send_text_reply(chat_id, approval_message) or [])
        all_replies.append(approval_message)
        SessionStateManager.set_awaiting_approval(
            session_id=session_id,
            approval_data={
                "commands_summary": approval_message,
                "risk_level": interrupt_data.get("risk_level", "未知"),
                "commands": interrupt_data.get("commands", []),
            },
        )
        return "interrupted"

    if event_type == "node":
        logger.info(f"📍 节点执行: {event.get('node')}")
        return None

    if event_type == "complete":
        logger.info("✅ 工作流执行完成")
        final_state = ensure_final_report_in_state(event.get("state", {}))
        if diag_collector:
            diag_collector["final_state"] = final_state
        await _send_final_state_reply(
            chat_id, final_state, all_replies, all_reply_message_ids
        )
        return "completed"

    if event_type == "error":
        error_msg = event.get("error", "未知错误")
        logger.error(f"❌ 工作流事件错误: {error_msg}")
        all_reply_message_ids.extend(
            await _send_text_reply(chat_id, f"工作流执行失败: {error_msg}") or []
        )
        all_replies.append(f"工作流执行失败: {error_msg}")
        return None

    for node_name, state_update in event.items():
        logger.info(f"📍 节点 {node_name} 更新: {type(state_update)}")

        if node_name == "__interrupt__":
            logger.warning(f"⏸️ 工作流被中断: {state_update}")
            all_reply_message_ids.extend(
                await _send_text_reply(chat_id, INTERRUPT_PLACEHOLDER_MESSAGE) or []
            )
            continue

        actual_update = unwrap_overwrite(state_update)
        logger.info(f"📍 解包后类型: {type(actual_update)}")

        # 🔍 详细日志：诊断 state_update 的内容
        logger.debug(f"📍 [诊断] 节点={node_name}, state_update类型={type(state_update)}, 内容预览={str(state_update)[:200] if state_update else 'None'}")
        logger.debug(f"📍 [诊断] actual_update类型={type(actual_update)}, 是否dict={isinstance(actual_update, dict)}, 有messages={isinstance(actual_update, dict) and 'messages' in actual_update}")

        # 特殊处理：如果是 model 节点但没有 messages，尝试从其他地方获取
        if node_name == "model" and actual_update is None:
            logger.warning(f"⚠️ [诊断] model 节点的 state_update 为 None，尝试检查完整事件")
            logger.debug(f"📍 [诊断] 完整事件: {event}")

        if not isinstance(actual_update, dict) or "messages" not in actual_update:
            continue

        # 收集后备回复
        fallback_reply = await _process_message_update(
            actual_update["messages"],
            session_id,
            chat_id,
            all_replies,
            all_reply_message_ids,
            diag_collector,
        )
        if fallback_reply and diag_collector is not None:
            if "fallback_replies" not in diag_collector:
                diag_collector["fallback_replies"] = []
            diag_collector["fallback_replies"].append(fallback_reply)

    return None


async def _process_message_update(
    raw_messages: Any,
    session_id: str,
    chat_id: str,
    all_replies: list[str],
    all_reply_message_ids: list[str],
    diag_collector: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    处理 state update 中的 messages 字段。

    使用数据库持久化已处理的消息索引，避免服务重启后重复发送历史消息。

    Returns:
        后备回复（如果所有消息都被过滤），否则返回 None
    """
    messages = unwrap_overwrite(raw_messages)
    msg_count = len(messages) if isinstance(messages, list) else 0
    logger.info(f"📍 [消息处理] 消息列表长度: {msg_count}")

    if not messages or not isinstance(messages, list):
        logger.warning(f"⚠️ [消息处理] 消息为空或不是列表")
        return

    last_processed = SessionStateManager.get_last_processed_message_index(session_id)

    # 只处理新增的消息（索引 > last_processed）
    new_messages = []
    for idx, message in enumerate(messages):
        if idx > last_processed:
            new_messages.append((idx, message))

    if not new_messages:
        logger.debug(f"⏭️ [消息处理] 没有新消息需要处理（已处理到索引 {last_processed}）")
        return

    logger.info(f"📍 [消息处理] 发现 {len(new_messages)} 条新消息（索引 {last_processed+1} 到 {msg_count-1}）")

    # 跟踪最后处理的索引和是否有 AI 回复
    max_processed_idx = last_processed
    has_ai_reply = False
    fallback_reply = None  # 保存被过滤消息的友好版本
    fallback_replies = []  # 保存所有被过滤消息的友好版本

    for idx, message in new_messages:
        msg_type = type(message).__name__
        content = getattr(message, "content", None)

        # 收集诊断信息
        if diag_collector:
            diag_collector["messages_seen"].append({
                "index": idx,
                "type": msg_type,
                "has_content": bool(content),
                "content_length": len(str(content)) if content else 0,
            })

        logger.debug(f"📍 [消息#{idx+1}] 类型={msg_type}, content长度={len(str(content)) if content else 0}")

        if isinstance(message, HumanMessage):
            logger.info(f"👤 [用户消息] {str(content)[:100]}")
            max_processed_idx = idx
            continue

        # 处理 AIMessage
        if isinstance(message, AIMessage):
            # 检查是否有 tool_calls（工具调用）
            tool_calls = getattr(message, "tool_calls", None)
            if tool_calls and len(tool_calls) > 0:
                tool_names = [tc.get('name', '?') for tc in tool_calls]
                logger.info(f"🔧 [工具调用] 数量={len(tool_calls)}, 工具={tool_names}")

                # 收集工具调用信息
                if diag_collector:
                    diag_collector["tool_calls"].extend(tool_names)

                max_processed_idx = idx
                # 注意：工具调用消息没有 content，需要等待后续消息
                continue

            if not content:
                logger.debug(f"⚠️ [AI消息#{idx}] content为空（只有tool_calls），继续处理后续消息")
                max_processed_idx = idx
                continue

            if should_skip_message(content):
                logger.info(f"⏭️ [AI消息#{idx}] 被should_skip_message跳过，尝试转换为友好格式")

                # 尝试将被过滤的消息转换为友好格式作为后备回复
                try:
                    formatted_result = await format_tool_output(content)
                    if isinstance(formatted_result, dict) and formatted_result.get("msg_type") in {"card", "interactive"}:
                        # 卡片消息：转换为可读文本
                        converted = _convert_card_to_readable_text(formatted_result["card"])
                    elif isinstance(formatted_result, dict) and "text" in formatted_result:
                        converted = formatted_result["text"]
                    else:
                        converted = str(formatted_result)

                    logger.info(f"💾 [后备回复] 保存了 {len(converted)} 字符的友好版本")
                    fallback_replies.append(converted)
                    fallback_reply = converted  # 保留最后一个用于兼容
                except Exception as e:
                    logger.warning(f"⚠️ [后备回复] 转换失败: {e}")

                max_processed_idx = idx
                continue

            # 有实际内容的 AI 回复
            max_processed_idx = idx
            has_ai_reply = True
            logger.info(f"📝 [AI回复] 内容长度={len(str(content))}")

            # 收集 AI 回复信息
            if diag_collector:
                diag_collector["ai_replies"].append({
                    "index": idx,
                    "content_length": len(str(content)),
                    "content_preview": str(content)[:200],
                })

            all_reply_message_ids.extend(
                await _send_formatted_result(chat_id, content, all_replies) or []
            )

        # 处理 ToolMessage（工具返回结果）
        elif isinstance(message, ToolMessage):
            max_processed_idx = idx
            continue

        # 其他类型的消息
        else:
            max_processed_idx = idx

    # 批量更新最后处理的索引（只更新一次，减少数据库写入）
    if max_processed_idx > last_processed:
        SessionStateManager.set_last_processed_message_index(session_id, max_processed_idx)
        logger.info(f"📍 [消息处理] 已更新处理索引: {last_processed} -> {max_processed_idx}")

    # 记录处理结果
    if has_ai_reply:
        logger.info(f"✅ [消息处理] 本次处理完成，已发送 AI 回复")
    elif all_replies:
        logger.info(f"✅ [消息处理] 本次发送 {len(all_replies)} 条新回复（来自历史消息）")
    else:
        # 如果没有回复，打印诊断信息
        logger.warning(f"⚠️ [消息处理] 本次没有生成任何回复")
        logger.warning(f"   - 新消息数: {len(new_messages)}")
        logger.warning(f"   - 已处理索引: {last_processed} -> {max_processed_idx}")

        # 统计新消息的类型
        msg_type_count = {}
        for idx, msg in new_messages:
            msg_type = type(msg).__name__
            msg_type_count[msg_type] = msg_type_count.get(msg_type, 0) + 1

            # 记录前 5 条新消息的详细信息
            if sum(msg_type_count.values()) <= 5:
                content = getattr(msg, "content", None)
                tool_calls = getattr(msg, "tool_calls", None) if isinstance(msg, AIMessage) else None
                logger.warning(
                    f"   - 消息#{idx} [{msg_type}] "
                    f"content={bool(content)}({len(str(content)) if content else 0}字符) "
                    f"tool_calls={bool(tool_calls)}({len(tool_calls) if tool_calls else 0})"
                )

        logger.warning(f"   - 消息类型分布: {msg_type_count}")

    # 返回后备回复（如果没有其他回复）
    if not has_ai_reply and not all_replies and fallback_replies:
        # 合并所有后备回复
        combined = "\n\n".join(fallback_replies)
        logger.info(f"💾 [后备回复] 返回 {len(fallback_replies)} 条后备回复，总长度: {len(combined)} 字符")
        return combined
    return None


async def _send_formatted_result(
    chat_id: str,
    content: str,
    all_replies: list[str],
) -> list[str]:
    """根据格式化结果发送卡片或文本消息。"""
    formatted_result = await format_tool_output(content)
    logger.info(f"📍 格式化结果类型: {type(formatted_result)}")
    logger.info(
        "📍 格式化结果: %s",
        formatted_result if isinstance(formatted_result, dict) else str(formatted_result)[:200],
    )

    if isinstance(formatted_result, dict) and formatted_result.get("msg_type") in {
        "card",
        "interactive",
    }:
        logger.info("📤 准备发送飞书卡片")
        client = get_feishu_client()
        response = await client.send_card_message(chat_id, formatted_result["card"])

        # 将卡片转换为可读文本保存到数据库
        readable_text = _convert_card_to_readable_text(formatted_result["card"])
        all_replies.append(readable_text)
        logger.info("✅ 已发送飞书卡片")
        return _extract_sent_message_ids(response)

    text_content = (
        formatted_result.get("text", "")
        if isinstance(formatted_result, dict)
        else str(formatted_result)
    )
    logger.info(f"📤 准备发送文本消息: {text_content[:100]}")
    message_ids = await _send_text_reply(chat_id, text_content)
    all_replies.append(text_content)
    logger.info("✅ 已发送文本回复")
    return message_ids


async def _persist_assistant_reply(
    session_id: Optional[str],
    replies: list[str],
    reply_message_ids: Optional[list[str]] = None,
) -> None:
    """保存助手回复到数据库。"""
    if not session_id or not replies:
        return

    db = SessionLocal()
    try:
        combined_reply = "\n\n".join(replies)
        meta_data = None
        if reply_message_ids:
            meta_data = json.dumps(
                {"feishu_message_ids": list(dict.fromkeys(reply_message_ids))},
                ensure_ascii=False,
            )
        save_feishu_message(
            db,
            session_id,
            MessageRole.ASSISTANT,
            combined_reply,
            meta_data=meta_data,
        )
        logger.info("✅ 已保存飞书AI回复到数据库")
    except Exception as exc:
        logger.error(f"❌ 保存飞书AI回复失败: {exc}")
    finally:
        db.close()


async def _persist_error_reply(session_id: Optional[str], error_msg: str) -> None:
    """保存错误消息到数据库。"""
    if not session_id:
        return

    db = SessionLocal()
    try:
        save_feishu_message(db, session_id, MessageRole.ASSISTANT, error_msg)
    except Exception as exc:
        logger.error(f"❌ 保存错误消息失败: {exc}")
    finally:
        db.close()


async def _send_help_message(chat_id: str) -> None:
    """发送帮助消息。"""
    await _send_text_reply(chat_id, format_help_message())


async def _send_text_reply(chat_id: str, text: str) -> list[str]:
    """发送文本回复，自动处理长消息分段。"""
    message_ids: list[str] = []
    try:
        client = get_feishu_client()

        if len(text) <= MAX_FEISHU_MESSAGE_LENGTH:
            response = await client.send_text_message(chat_id, text)
            message_ids.extend(_extract_sent_message_ids(response))
            logger.info(f"✅ 已发送回复到 {chat_id} (长度: {len(text)})")
            return message_ids

        logger.warning(f"⚠️ 消息过长 ({len(text)} 字符)，将分段发送")
        parts = _split_long_text(text, MAX_FEISHU_MESSAGE_LENGTH)

        for index, part in enumerate(parts, 1):
            header = f"📄 **消息 {index}/{len(parts)}**\n\n" if len(parts) > 1 else ""
            response = await client.send_text_message(chat_id, header + part)
            message_ids.extend(_extract_sent_message_ids(response))
            logger.info(f"✅ 已发送第 {index}/{len(parts)} 部分到 {chat_id} (长度: {len(part)})")
            if index < len(parts):
                await asyncio.sleep(0.5)
    except Exception as exc:
        logger.exception(f"发送回复失败: {exc}")
    return message_ids


def _split_long_text(text: str, max_length: int) -> list[str]:
    """按行拆分长文本。"""
    parts: list[str] = []
    current_part = ""

    for line in text.split("\n"):
        if len(current_part) + len(line) + 1 <= max_length:
            current_part += line + "\n"
            continue
        if current_part:
            parts.append(current_part.strip())
        current_part = line + "\n"

    if current_part:
        parts.append(current_part.strip())
    return parts


async def handle_card_action(action: Dict[str, Any]) -> Dict[str, Any]:
    """处理卡片交互事件。"""
    logger.info(f"📋 收到卡片交互: {action}")

    action_value = action.get("action", {}).get("value", {})
    action_type = action_value.get("action_type", "")

    if action_type == "approve":
        return {"toast": {"type": "success", "content": "✅ 已批准（新架构中审批流程待实现）"}}
    if action_type == "reject":
        return {"toast": {"type": "info", "content": "❌ 已拒绝"}}
    return {"toast": {"type": "warning", "content": "未知操作"}}


async def send_approval_response(
    chat_id: str,
    task_id: str,
    decision: str,
    approver: str,
    result: Dict[str, Any],
) -> bool:
    """发送审批响应消息（新架构中暂不使用）。"""
    logger.info("send_approval_response called (新架构中暂不使用)")
    return True


async def _handle_approval_response(
    session_id: str,
    decision: str,
    chat_id: str,
    user_response: str,
) -> Literal["completed", "interrupted"]:
    """处理批准响应，恢复工作流。"""
    logger.info(f"开始处理批准响应: session_id={session_id}, decision={decision}")

    try:

        # 在 DeepAgents 架构中，agent 是单例的，直接创建即可
        agent = await create_agent_for_session(
            session_id=session_id,
            enable_approval=True,
            enable_security=True,
        )

        resume_state: OpsState = {
            "session_id": session_id,
            "user_id": "feishu_user",
            "user_role": "admin",
            "trigger_source": "feishu",
            "workflow_status": "running",
            "approval_status": decision,
            "approval_decision": decision,
            "is_approval_response": True,
            "waiting_for_approval": False,
            "approval_required": False,
            "execution_success": False,
            "need_remediation": False,
            "diagnosis_round": 0,
            "max_diagnosis_rounds": 3,
            "current_command_index": 0,
            "data_sufficient": False,
            "security_check_passed": True,
            "permission_granted": True,
            "collected_data": {},
            "execution_history": [],
        }

        all_replies: list[str] = []
        all_reply_message_ids: list[str] = []
        async for event in agent.astream(resume_state):
            event_result = await _handle_workflow_stream_event(
                event=event,
                chat_id=chat_id,
                session_id=session_id,
                all_replies=all_replies,
                all_reply_message_ids=all_reply_message_ids,
            )
            if event_result == "interrupted":
                await _persist_assistant_reply(session_id, all_replies, all_reply_message_ids)
                return "interrupted"

        await _persist_assistant_reply(session_id, all_replies, all_reply_message_ids)
        return "completed"
    except Exception as exc:
        logger.error(f"❌ 处理批准响应失败: {exc}", exc_info=True)
        await _send_text_reply(chat_id, format_error_message(exc))
        raise
