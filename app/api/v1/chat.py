# app/api/v1/chat.py
"""
聊天 API 端点

提供 Web 端聊天功能，包括：
- 会话管理（创建、查询、删除）
- 消息发送（SSE 流式响应）
- 工作流恢复（审批后继续执行）
"""

import json
import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permission_checker import get_user_permission_codes
from app.deepagents.factory import create_agent_for_session
from app.memory.memory_manager import get_memory_manager
from app.utils.timezone import get_beijing_now
from app.models.chat_message import ChatMessage, MessageRole
from app.models.chat_session import ChatSession
from app.models.database import get_db
from app.models.user import User
from app.schemas.chat import (
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionListResponse,
    ChatSessionResponse,
)
from app.services.agent_chat_service import (
    ChatRequest,
    EventType,
    MessageChannel,
    get_agent_chat_service,
)
from app.utils.logger import clear_request_context, get_logger, set_request_context
from app.utils.llm_helper import ensure_final_report_in_state

router = APIRouter(prefix="/chat", tags=["chat"])
logger = get_logger(__name__)


# ========== 辅助函数：会话响应构建 ==========

def _build_session_response(
    session: ChatSession,
    user: User,
    message_count: int,
    last_message: Optional[ChatMessage],
    db: Session,
) -> ChatSessionResponse:
    """构建会话响应对象"""
    # 处理飞书用户名
    external_user_name = session.external_user_name
    if session.source == "feishu" and session.external_user_id:
        feishu_user = db.query(User).filter(
            User.feishu_user_id == session.external_user_id
        ).first()
        if feishu_user:
            external_user_name = feishu_user.username

    # 处理最后消息截断
    last_msg_content = None
    if last_message:
        last_msg_content = (
            last_message.content[:50] + "..."
            if len(last_message.content) > 50
            else last_message.content
        )

    return ChatSessionResponse(
        session_id=session.session_id,
        title=session.title,
        source=session.source,
        username=user.username,
        external_user_name=external_user_name,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=message_count,
        last_message=last_msg_content,
        state=session.state or "normal",
        pending_approval_data=session.pending_approval_data,
    )


def _get_session_stats(db: Session, session_id: str) -> tuple:
    """获取会话统计信息（消息数量、最后消息）"""
    message_count = (
        db.query(func.count(ChatMessage.id))
        .filter(ChatMessage.session_id == session_id)
        .scalar()
    )

    last_message = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(desc(ChatMessage.created_at))
        .first()
    )

    return message_count, last_message


# ========== 辅助函数：消息保存 ==========

def _save_user_message(
    db: Session,
    session_id: str,
    content: str,
) -> ChatMessage:
    """保存用户消息到数据库"""
    message = ChatMessage(
        session_id=session_id,
        role=MessageRole.USER,
        content=content,
        meta_data=None,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    logger.info(f"用户消息已保存: message_id={message.id}")
    return message


def _save_approval_request(
    db: Session,
    session_id: str,
    session: ChatSession,
    approval_msg: str,
    commands: List[Dict],
) -> bool:
    """保存审批请求消息"""
    try:
        # 检查是否已存在审批请求
        existing = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session_id,
                ChatMessage.role == MessageRole.ASSISTANT,
                ChatMessage.content.contains("📋 命令规划"),
            )
            .first()
        )

        if existing:
            return False

        # 创建新的审批请求消息
        approval_content = f"## 📋 命令规划\n\n{approval_msg}\n\n"
        message = ChatMessage(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=approval_content,
            meta_data=json.dumps({
                "type": "approval_request",
                "message": approval_msg,
                "commands": commands,
            }),
        )
        db.add(message)
        session.updated_at = get_beijing_now()
        db.commit()
        logger.info(f"✅ 审批请求消息已保存: session={session_id}")
        return True

    except Exception as e:
        logger.warning(f"⚠️ 保存审批请求消息失败: {e}")
        return False


def _save_assistant_message(
    db: Session,
    session_id: str,
    session: ChatSession,
    content: str,
    final_state: Optional[Dict],
    workflow_completed: bool,
    user_query: str,
) -> Optional[ChatMessage]:
    """保存 AI 回复消息"""
    if not content:
        return None

    message = ChatMessage(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=content,
        meta_data=json.dumps({
            "workflow_status": (
                final_state.get("workflow_status")
                if final_state else ("completed" if workflow_completed else "interrupted")
            ),
            "intent_type": (
                final_state.get("intent_type", "unknown")
                if final_state else "unknown"
            ),
            "diagnosis_round": (
                final_state.get("diagnosis_round", 0)
                if final_state else 0
            ),
        }),
    )
    db.add(message)

    # 更新会话标题（如果还没有）
    if not session.title:
        session.title = user_query[:30] + ("..." if len(user_query) > 30 else "")

    session.updated_at = get_beijing_now()
    db.commit()
    db.refresh(message)

    logger.info(f"✅ AI 回复已保存: session={session_id}, message_id={message.id}")
    return message


async def _auto_learn(
    user_id: int,
    session_id: str,
    user_query: str,
    response: str,
) -> None:
    """自动学习（存储到记忆系统）"""
    try:
        memory_manager = get_memory_manager(user_id=str(user_id))
        await memory_manager.auto_learn_from_result(
            user_query=user_query,
            result={"messages": [{"content": response}]},
            session_id=session_id,
            messages=[
                {"role": "user", "content": user_query},
                {"role": "assistant", "content": response}
            ],
        )
        logger.info(f"🧠 自动学习完成: session={session_id}")

    except Exception as e:
        logger.warning(f"⚠️ 记忆自动学习失败: {e}")


# ========== 辅助函数：SSE 事件生成 ==========

def _sse_event(event_type: str, data: Dict) -> str:
    """生成 SSE 事件字符串"""
    return f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False)}\n\n"


# ========== 辅助函数：工作流恢复 ==========

def _build_resume_state(
    session_id: str,
    user: User,
    approval_data: dict,
) -> Dict[str, Any]:
    """构建工作流恢复状态"""
    return {
        "session_id": session_id,
        "user_id": str(user.id),
        "user_role": "admin" if user.is_superuser else "user",
        "trigger_source": "web",
        "workflow_status": "running",
        "approval_status": approval_data.get("status", "approved"),
        "approval_decision": approval_data.get("status", "approved"),
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


def _get_node_status_message(node_name: str) -> str:
    """获取节点执行状态消息"""
    status_map = {
        "execute_diagnosis": "🔧 正在执行诊断...",
        "analyze_result": "📊 正在分析结果...",
        "execute_remediation": "🔨 正在执行修复...",
    }
    return status_map.get(node_name, f"⚙️ 正在执行: {node_name}")


def _build_final_report(final_state: Dict) -> str:
    """构建最终报告"""
    state = ensure_final_report_in_state(final_state)
    report = state.get("formatted_response", "") or state.get("final_report", "")

    if report:
        return report

    return f"""## ✅ 工作流执行完成

**执行成功**: {'是' if state.get('execution_success') else '否'}
"""


def _append_to_last_assistant_message(
    db: Session,
    session_id: str,
    session: ChatSession,
    content: str,
    final_state: Optional[Dict],
) -> None:
    """追加内容到最后一条 AI 消息"""
    last_msg = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session_id,
            ChatMessage.role == MessageRole.ASSISTANT,
        )
        .order_by(desc(ChatMessage.created_at))
        .first()
    )

    if last_msg:
        last_msg.content += f"\n\n{content}"
        last_msg.meta_data = json.dumps({
            "workflow_status": (
                final_state.get("workflow_status") if final_state else "unknown"
            ),
            "execution_success": (
                final_state.get("execution_success") if final_state else False
            ),
        })
    else:
        # 创建新消息
        message = ChatMessage(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=content,
            meta_data=json.dumps({
                "workflow_status": (
                    final_state.get("workflow_status") if final_state else "unknown"
                ),
                "execution_success": (
                    final_state.get("execution_success") if final_state else False
                ),
            }),
        )
        db.add(message)

    session.updated_at = get_beijing_now()
    db.commit()
    logger.info(f"AI 回复已更新/保存: session={session_id}")


# ========== 会话管理端点 ==========

@router.post("/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    session_data: ChatSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新的聊天会话"""
    session_id = f"chat_{uuid.uuid4().hex[:16]}"

    new_session = ChatSession(
        session_id=session_id,
        user_id=current_user.id,
        title=session_data.title,
        is_active=True,
    )

    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    logger.info(f"创建聊天会话: session={session_id}, user={current_user.username}")

    return _build_session_response(new_session, current_user, 0, None, db)


@router.get("/sessions", response_model=ChatSessionListResponse)
async def get_sessions(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的会话列表"""
    # 构建查询（飞书会话对所有用户可见，Web 会话只对创建者可见）
    sessions_query = (
        db.query(ChatSession, User)
        .join(User, ChatSession.user_id == User.id)
        .filter(
            (
                (ChatSession.source == "feishu") |
                ((ChatSession.source == "web") & (ChatSession.user_id == current_user.id))
            ),
            ((ChatSession.source == "feishu") | (ChatSession.is_active == True)),
        )
        .order_by(desc(ChatSession.updated_at))
    )

    total = sessions_query.count()
    sessions_with_users = sessions_query.offset(skip).limit(limit).all()

    # 构建响应
    session_responses = [
        _build_session_response(
            session, user, *_get_session_stats(db, session.session_id), db
        )
        for session, user in sessions_with_users
    ]

    return ChatSessionListResponse(sessions=session_responses, total=total)


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取会话详情"""
    result = (
        db.query(ChatSession, User)
        .join(User, ChatSession.user_id == User.id)
        .filter(
            ChatSession.session_id == session_id,
            (ChatSession.source == "feishu") | (ChatSession.user_id == current_user.id),
        )
        .first()
    )

    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    session, user = result
    message_count, last_message = _get_session_stats(db, session_id)

    return _build_session_response(session, user, message_count, last_message, db)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除会话（软删除）"""
    session = db.query(ChatSession).filter(
        ChatSession.session_id == session_id
    ).first()

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    # 权限检查
    if not current_user.is_superuser:
        if session.source == "feishu":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权删除飞书会话，请联系管理员"
            )
        if session.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权删除其他用户的会话"
            )

    # 软删除
    session.is_active = False
    db.commit()

    logger.info(
        f"用户 {current_user.username} 删除会话: session={session_id}, source={session.source}"
    )


# ========== 消息端点 ==========

@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
async def get_messages(
    session_id: str,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取会话的消息历史"""
    # 验证会话访问权限
    session = (
        db.query(ChatSession)
        .filter(
            ChatSession.session_id == session_id,
            (ChatSession.source == "feishu") | (ChatSession.user_id == current_user.id),
        )
        .first()
    )

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    # 查询消息
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .offset(skip)
        .limit(limit)
        .all()
    )

    return [
        ChatMessageResponse(
            id=msg.id,
            role=msg.role.value,
            content=msg.content,
            created_at=msg.created_at,
            metadata=json.loads(msg.meta_data) if msg.meta_data else None,
        )
        for msg in messages
    ]


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    message_data: ChatMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """发送消息并通过 Agent 工作流处理（SSE 流式响应）"""
    # 获取用户权限
    permission_codes = get_user_permission_codes(db, current_user.id)
    user_permissions = list(set(permission_codes))

    # 设置请求上下文（包含权限信息，供 middleware 使用）
    set_request_context(
        session_id=session_id,
        user_id=str(current_user.id),
        channel="web",
        user_permissions=user_permissions,
    )
    logger.info(f"📥 收到 Web 聊天请求: session={session_id}, user={current_user.username}")
    logger.info(
        f"🔐 用户权限: {', '.join(sorted(user_permissions)) if user_permissions else '无'}"
    )

    # 验证会话
    session = (
        db.query(ChatSession)
        .filter(
            ChatSession.session_id == session_id,
            (ChatSession.source == "feishu") | (ChatSession.user_id == current_user.id),
            ChatSession.is_active == True,
        )
        .first()
    )

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    async def generate_stream() -> AsyncGenerator[str, None]:
        """生成 SSE 流式响应"""
        try:
            # 1. 保存用户消息
            _save_user_message(db, session_id, message_data.content)

            # 2. 构建请求并调用 AgentChatService
            request = ChatRequest(
                session_id=session_id,
                user_id=current_user.id,
                content=message_data.content,
                channel=MessageChannel.WEB,
                user_permissions=user_permissions,
                enable_security=True,
            )

            service = get_agent_chat_service()
            full_response = ""
            final_state = None

            # 4. 处理流式事件
            async for event in service.process_message_stream(request):
                event_data = {"type": event.type.value, **event.data}

                if event.type == EventType.STATUS:
                    yield _sse_event("status", event_data)

                elif event.type == EventType.CHUNK:
                    full_response = event.data.get("content", "")
                    yield _sse_event("chunk", event_data)

                elif event.type == EventType.APPROVAL_REQUEST:
                    _save_approval_request(
                        db, session_id, session,
                        event.data.get("message", ""),
                        event.data.get("commands", []),
                    )
                    yield _sse_event("approval_request", event_data)
                    return  # 等待用户审批

                elif event.type == EventType.DONE:
                    final_state = event.data.get("final_state", {})
                    workflow_completed = event.data.get("workflow_completed", False)

                    if full_response:
                        assistant_msg = _save_assistant_message(
                            db, session_id, session, full_response,
                            final_state, workflow_completed, message_data.content
                        )
                        if assistant_msg:
                            await _auto_learn(
                                current_user.id, session_id,
                                message_data.content, full_response
                            )
                            event_data["message_id"] = assistant_msg.id

                    yield _sse_event("done", event_data)

                elif event.type == EventType.ERROR:
                    # 错误时也保存一条记录，确保对话不丢失
                    error_msg = event.data.get("message", "处理失败")
                    _save_assistant_message(
                        db, session_id, session,
                        f"⚠️ {error_msg}",
                        None, False, message_data.content
                    )
                    yield _sse_event("error", event_data)

        except Exception as e:
            logger.error(f"流式响应生成错误: {e}", exc_info=True)
            yield _sse_event("error", {"message": str(e)})

        finally:
            clear_request_context()

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/resume")
async def resume_workflow(
    session_id: str,
    approval_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """恢复暂停的工作流（用户批准后）"""
    # 获取用户权限
    permission_codes = get_user_permission_codes(db, current_user.id)
    user_permissions = list(set(permission_codes))

    set_request_context(
        session_id=session_id,
        user_id=str(current_user.id),
        channel="web",
        user_permissions=user_permissions,
    )
    logger.info(f"▶️ 收到工作流恢复请求: session={session_id}, user={current_user.username}")

    # 验证会话
    session = (
        db.query(ChatSession)
        .filter(
            ChatSession.session_id == session_id,
            (ChatSession.source == "feishu") | (ChatSession.user_id == current_user.id),
            ChatSession.is_active == True,
        )
        .first()
    )

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    async def generate_resume_stream() -> AsyncGenerator[str, None]:
        """生成恢复工作流的 SSE 流式响应"""
        try:
            # 创建 Agent
            agent = await create_agent_for_session(
                session_id=session_id,
                enable_approval=True,
                enable_security=True,
            )

            # 构建恢复状态
            resume_state = _build_resume_state(session_id, current_user, approval_data)
            logger.info(f"▶️ 恢复工作流: session={session_id}, approval={approval_data}")

            # 发送恢复状态
            yield _sse_event("status", {"status": "resuming", "message": "▶️ 正在恢复工作流..."})

            # 执行工作流
            full_response = ""
            workflow_completed = False
            final_state = None
            start_time = time.time()
            timeout = 300
            config = {"configurable": {"thread_id": session_id}}

            async for event in agent.astream(resume_state, config=config):
                elapsed = time.time() - start_time

                # 超时检查
                if elapsed > timeout:
                    logger.error(f"⏰ 工作流恢复超时: {elapsed:.2f}s")
                    yield _sse_event("error", {"message": f"工作流恢复超时（{elapsed:.2f}s）"})
                    break

                event_type = event.get("type")
                logger.info(f"📨 事件: type={event_type}, elapsed={elapsed:.2f}s")

                # 处理中断
                if event_type == "interrupt":
                    interrupt_data = event.get("data", {})
                    yield _sse_event("approval_request", {
                        "message": interrupt_data.get("message", ""),
                        "commands": interrupt_data.get("commands", []),
                        "session_id": session_id,
                    })
                    full_response += f"\n\n{interrupt_data.get('message', '')}\n\n"
                    return

                # 处理节点执行
                elif event_type == "node":
                    node_name = event.get("node")
                    logger.info(f"📍 节点执行: {node_name}")
                    yield _sse_event("status", {
                        "status": "processing",
                        "message": _get_node_status_message(node_name),
                    })

                # 处理完成
                elif event_type == "complete":
                    final_state = event.get("state", {})
                    workflow_completed = True
                    logger.info("✅ 工作流恢复执行完成")

                    report = _build_final_report(final_state)
                    full_response += report
                    yield _sse_event("chunk", {"content": report})

                # 处理错误
                elif event_type == "error":
                    error_msg = event.get("error", "未知错误")
                    logger.error(f"❌ 工作流恢复失败: {error_msg}")
                    yield _sse_event("error", {"message": f"工作流恢复失败: {error_msg}"})
                    return

            # 保存 AI 回复
            if workflow_completed and full_response:
                _append_to_last_assistant_message(
                    db, session_id, session, full_response, final_state
                )
                yield _sse_event("done", {})

        except Exception as e:
            logger.error(f"恢复工作流流式响应错误: {e}", exc_info=True)
            yield _sse_event("error", {"message": str(e)})

        finally:
            clear_request_context()

    return StreamingResponse(
        generate_resume_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
