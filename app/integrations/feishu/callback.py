"""飞书消息处理 - 新架构版本"""

import asyncio
import base64
import hashlib
import json
import traceback
from typing import Any, Dict, Literal, Optional

from Crypto.Cipher import AES
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Overwrite

from app.core.llm_factory import LLMFactory
from app.core.permission_checker import get_user_permission_codes
from app.core.state import OpsState
from app.deepagents.factory import create_agent_for_session
from app.deepagents.main_agent import get_ops_agent, get_thread_config
from app.integrations.feishu.callback_extensions import (
    handle_end_session_command,
    handle_new_session_command,
)
from app.integrations.feishu.client import get_feishu_client
from app.integrations.feishu.message_formatter import (
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
from app.utils.logger import get_logger

logger = get_logger(__name__)

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
    """判断是否应该跳过这条消息（不发送给用户）。"""
    if not content or not isinstance(content, str):
        return False

    skip_patterns = [
        "Updated todo list to",
        "我来帮你",
        "让我",
        "首先",
        "接下来",
        "正在",
    ]

    for pattern in skip_patterns:
        if pattern in content:
            return len(content) <= 200

    try:
        data = json.loads(content)
        if isinstance(data, dict) and "output" in data:
            return False
        return True
    except (json.JSONDecodeError, TypeError):
        return False


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
        logger.exception(f"❌ Error handling message: {exc}")
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
    logger.info("🎯 handle_message_receive 被调用 (新架构)")
    logger.info(f"📨 收到消息: {message}")
    logger.info("=" * 60)

    print("=" * 60)
    print("🎯 [feishu_callback] handle_message_receive 被调用")
    print(f"📨 [feishu_callback] 收到消息: {message}")
    print("=" * 60)


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
        print("📦 [feishu_callback] 正在获取 Agent...")
        agent = await get_ops_agent(enable_approval=True, user_permissions=user_permissions)
        logger.info(f"✅ Agent 获取成功: {type(agent)}")
        print(f"✅ [feishu_callback] Agent 获取成功: {type(agent)}")

        initial_state = {"messages": [HumanMessage(content=text)]}
        config = get_thread_config(session_id)
        all_replies: list[str] = []

        logger.info(f"🚀 开始流式执行工作流，session_id={session_id}")
        logger.info(f"📝 初始状态: {initial_state}")
        logger.info(f"⚙️ 配置: {config}")
        print(f"🚀 [feishu_callback] 开始流式执行工作流，session_id={session_id}")

        event_count = 0
        async for event in agent.astream(initial_state, config=config):
            event_count += 1
            logger.info(f"📍 事件 #{event_count}: {list(event.keys())}")
            await _handle_workflow_stream_event(
                event=event,
                chat_id=chat_id,
                all_replies=all_replies,
            )

        logger.info(f"🏁 工作流执行完成，共 {event_count} 个事件，{len(all_replies)} 条回复")
        print(f"🏁 [feishu_callback] 工作流执行完成，共 {event_count} 个事件")

        await _persist_assistant_reply(session_id, all_replies)
    except NotImplementedError as exc:
        logger.error(f"❌ astream NotImplementedError: {exc}")
        print(f"❌ [feishu_callback] astream NotImplementedError: {exc}")
        traceback.print_exc()
        raise
    except Exception as exc:
        logger.exception(f"❌ 工作流执行失败: {exc}")
        print(f"❌ [feishu_callback] 工作流执行失败: {exc}")
        traceback.print_exc()

        error_msg = format_error_message(exc)
        detailed_error = f"{error_msg}\n\n**调试信息**:\n```\n{type(exc).__name__}: {str(exc)}\n```"
        await _send_text_reply(chat_id, detailed_error)
        await _persist_error_reply(session_id, error_msg)


async def _handle_workflow_stream_event(
    event: Dict[str, Any],
    chat_id: str,
    all_replies: list[str],
) -> None:
    """处理普通工作流中的单个流事件。"""
    for node_name, state_update in event.items():
        logger.info(f"📍 节点 {node_name} 更新: {type(state_update)}")

        if node_name == "__interrupt__":
            logger.warning(f"⏸️ 工作流被中断: {state_update}")
            await _send_text_reply(chat_id, INTERRUPT_PLACEHOLDER_MESSAGE)
            continue

        actual_update = unwrap_overwrite(state_update)
        logger.info(f"📍 解包后类型: {type(actual_update)}")
        if not isinstance(actual_update, dict) or "messages" not in actual_update:
            continue

        await _process_message_update(actual_update["messages"], chat_id, all_replies)


async def _process_message_update(
    raw_messages: Any,
    chat_id: str,
    all_replies: list[str],
) -> None:
    """处理 state update 中的 messages 字段。"""
    messages = unwrap_overwrite(raw_messages)
    logger.info(f"📍 消息列表长度: {len(messages) if isinstance(messages, list) else 'N/A'}")

    if not messages or not isinstance(messages, list):
        return

    last_message = messages[-1]
    logger.info(f"📍 最后一条消息类型: {type(last_message)}")

    if isinstance(last_message, HumanMessage):
        logger.info("⏭️ 跳过用户消息（不重复发送）")
        return

    if not isinstance(last_message, AIMessage):
        return

    content = getattr(last_message, "content", None)
    if not content:
        return

    logger.info(f"📍 消息内容预览: {str(content)[:100]}")
    if should_skip_message(content):
        logger.info("⏭️ 跳过调试消息（不发送给用户）")
        return

    await _send_formatted_result(chat_id, content, all_replies)


async def _send_formatted_result(
    chat_id: str,
    content: str,
    all_replies: list[str],
) -> None:
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
        await client.send_card_message(chat_id, formatted_result["card"])
        card_title = (
            formatted_result["card"].get("header", {}).get("title", {}).get("content", "查询结果")
        )
        all_replies.append(f"[卡片消息] {card_title}")
        logger.info("✅ 已发送飞书卡片")
        return

    text_content = (
        formatted_result.get("text", "")
        if isinstance(formatted_result, dict)
        else str(formatted_result)
    )
    logger.info(f"📤 准备发送文本消息: {text_content[:100]}")
    await _send_text_reply(chat_id, text_content)
    all_replies.append(text_content)
    logger.info("✅ 已发送文本回复")


async def _persist_assistant_reply(session_id: Optional[str], replies: list[str]) -> None:
    """保存助手回复到数据库。"""
    if not session_id or not replies:
        return

    db = SessionLocal()
    try:
        combined_reply = "\n\n".join(replies)
        save_feishu_message(db, session_id, MessageRole.ASSISTANT, combined_reply)
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


async def _send_text_reply(chat_id: str, text: str) -> None:
    """发送文本回复，自动处理长消息分段。"""
    try:
        client = get_feishu_client()

        if len(text) <= MAX_FEISHU_MESSAGE_LENGTH:
            await client.send_text_message(chat_id, text)
            logger.info(f"✅ 已发送回复到 {chat_id} (长度: {len(text)})")
            return

        logger.warning(f"⚠️ 消息过长 ({len(text)} 字符)，将分段发送")
        parts = _split_long_text(text, MAX_FEISHU_MESSAGE_LENGTH)

        for index, part in enumerate(parts, 1):
            header = f"📄 **消息 {index}/{len(parts)}**\n\n" if len(parts) > 1 else ""
            await client.send_text_message(chat_id, header + part)
            logger.info(f"✅ 已发送第 {index}/{len(parts)} 部分到 {chat_id} (长度: {len(part)})")
            if index < len(parts):
                await asyncio.sleep(0.5)
    except Exception as exc:
        logger.exception(f"发送回复失败: {exc}")


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
        async for event in agent.astream(resume_state):
            event_type = event.get("type")

            if event_type == "interrupt":
                interrupt_data = event.get("data", {})
                approval_message = interrupt_data.get("message", "")
                logger.info("⏸️ 工作流再次暂停，需要再次批准")

                await _send_text_reply(chat_id, approval_message)
                all_replies.append(approval_message)
                SessionStateManager.set_awaiting_approval(
                    session_id=session_id,
                    approval_data={
                        "commands_summary": approval_message,
                        "risk_level": interrupt_data.get("risk_level", "未知"),
                        "commands": interrupt_data.get("commands", []),
                    },
                )
                await _persist_assistant_reply(session_id, all_replies)
                return "interrupted"

            if event_type == "node":
                logger.info(f"📍 节点执行: {event.get('node')}")
                continue

            if event_type != "complete":
                continue

            final_state = event.get("state", {})
            logger.info("✅ 工作流恢复执行完成")

            response_to_send = final_state.get("formatted_response", "") or final_state.get(
                "final_report", ""
            )
            if response_to_send:
                await _send_text_reply(chat_id, response_to_send)
                all_replies.append(response_to_send)
                continue

            status_msg = (
                "✅ **工作流执行完成**\n\n"
                f"意图类型: {final_state.get('intent_type', 'unknown')}\n"
                f"诊断轮次: {final_state.get('diagnosis_round', 0)}\n"
                f"数据充足: {'是' if final_state.get('data_sufficient') else '否'}\n"
            )
            await _send_text_reply(chat_id, status_msg)
            all_replies.append(status_msg)

        await _persist_assistant_reply(session_id, all_replies)
        return "completed"
    except Exception as exc:
        logger.error(f"❌ 处理批准响应失败: {exc}", exc_info=True)
        await _send_text_reply(chat_id, format_error_message(exc))
        raise
