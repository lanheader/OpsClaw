# app/api/v2/chat.py
"""聊天 API 端点"""

import json
import logging
import uuid
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.deepagents.factory import create_agent_for_session
from app.core.state import OpsState
from app.models.database import get_db
from app.models.user import User
from app.models.chat_session import ChatSession
from app.models.chat_message import ChatMessage, MessageRole
from app.core.deps import get_current_user
from app.core.permission_checker import get_user_permission_codes
from app.schemas.chat import (
    ChatSessionCreate,
    ChatSessionResponse,
    ChatSessionListResponse,
    ChatMessageCreate,
    ChatMessageResponse,
)

router = APIRouter(prefix="/v2/chat", tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    session_data: ChatSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新的聊天会话"""
    # 生成唯一的 session_id
    session_id = f"chat_{uuid.uuid4().hex[:16]}"

    # 创建会话
    new_session = ChatSession(
        session_id=session_id, user_id=current_user.id, title=session_data.title, is_active=True
    )

    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    logger.info(f"Created chat session {session_id} for user {current_user.username}")

    return ChatSessionResponse(
        session_id=new_session.session_id,
        title=new_session.title,
        source=new_session.source,
        username=current_user.username,  # 添加用户名
        external_user_name=new_session.external_user_name,
        created_at=new_session.created_at,
        updated_at=new_session.updated_at,
        message_count=0,
        last_message=None,
    )


@router.get("/sessions", response_model=ChatSessionListResponse)
async def get_sessions(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的会话列表"""
    # 查询用户的会话（关联 User 表获取用户名）
    # 注意：飞书会话对所有用户可见（source='feishu'），Web 会话只对创建者可见
    sessions_query = (
        db.query(ChatSession, User)
        .join(User, ChatSession.user_id == User.id)
        .filter(
            (ChatSession.source == "feishu") | (ChatSession.user_id == current_user.id),
            ChatSession.is_active == True,
        )
        .order_by(desc(ChatSession.updated_at))
    )

    total = sessions_query.count()
    sessions_with_users = sessions_query.offset(skip).limit(limit).all()

    # 为每个会话获取消息数量和最后一条消息
    session_responses = []
    for session, user in sessions_with_users:
        message_count = (
            db.query(func.count(ChatMessage.id))
            .filter(ChatMessage.session_id == session.session_id)
            .scalar()
        )

        last_message = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.session_id)
            .order_by(desc(ChatMessage.created_at))
            .first()
        )

        # 如果是飞书会话，尝试通过 external_user_id 查找绑定的用户名
        external_user_name = session.external_user_name
        if session.source == "feishu" and session.external_user_id:
            feishu_user = (
                db.query(User).filter(User.feishu_user_id == session.external_user_id).first()
            )
            if feishu_user:
                external_user_name = feishu_user.username

        session_responses.append(
            ChatSessionResponse(
                session_id=session.session_id,
                title=session.title,
                source=session.source,
                username=user.username,  # 添加用户名
                external_user_name=external_user_name,
                created_at=session.created_at,
                updated_at=session.updated_at,
                message_count=message_count,
                last_message=(
                    last_message.content[:50] + "..."
                    if last_message and len(last_message.content) > 50
                    else (last_message.content if last_message else None)
                ),
            )
        )

    return ChatSessionListResponse(sessions=session_responses, total=total)


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_session(
    session_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """获取会话详情"""
    # 关联 User 表查询
    # 注意：飞书会话对所有用户可见，Web 会话只对创建者可见
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

    # 获取消息数量和最后一条消息
    message_count = (
        db.query(func.count(ChatMessage.id)).filter(ChatMessage.session_id == session_id).scalar()
    )

    last_message = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(desc(ChatMessage.created_at))
        .first()
    )

    # 如果是飞书会话，尝试通过 external_user_id 查找绑定的用户名
    external_user_name = session.external_user_name
    if session.source == "feishu" and session.external_user_id:
        feishu_user = db.query(User).filter(User.feishu_user_id == session.external_user_id).first()
        if feishu_user:
            external_user_name = feishu_user.username

    return ChatSessionResponse(
        session_id=session.session_id,
        title=session.title,
        source=session.source,
        username=user.username,  # 添加用户名
        external_user_name=external_user_name,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=message_count,
        last_message=(
            last_message.content[:50] + "..."
            if last_message and len(last_message.content) > 50
            else (last_message.content if last_message else None)
        ),
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """删除会话（软删除）

    权限规则：
    - 普通用户只能删除自己创建的 Web 会话
    - 管理员可以删除任何会话（包括飞书会话）
    """
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    # 权限检查
    if not current_user.is_superuser:
        # 普通用户只能删除自己创建的 Web 会话
        if session.source == "feishu":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="无权删除飞书会话，请联系管理员"
            )
        if session.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="无权删除其他用户的会话"
            )

    # 软删除
    session.is_active = False
    db.commit()

    logger.info(
        f"User {current_user.username} deleted chat session {session_id} (source: {session.source})"
    )


@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
async def get_messages(
    session_id: str,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取会话的消息历史"""
    # 验证会话所有权
    # 注意：飞书会话对所有用户可见，Web 会话只对创建者可见
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
    """发送消息并通过 Agent 工作流处理（SSE）"""
    # 验证会话所有权
    # 注意：飞书会话对所有用户可见，Web 会话只对创建者可见
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

    async def generate_stream():
        """生成 SSE 流式响应"""
        try:
            # 1. 保存用户消息
            user_message = ChatMessage(
                session_id=session_id,
                role=MessageRole.USER,
                content=message_data.content,
                meta_data=None,
            )
            db.add(user_message)
            db.commit()
            db.refresh(user_message)

            logger.info(f"User message saved: session={session_id}, message_id={user_message.id}")

            # 2. 调用 DeepAgents 工作流处理消息（流式）

            logger.info(f"🚀 调用 DeepAgents 工作流处理消息: {message_data.content}")

            # 获取用户权限
            permission_codes = get_user_permission_codes(db, current_user.id)
            user_permissions = set(permission_codes)
            logger.info(
                f"🔐 用户 {current_user.username} 的权限: {', '.join(sorted(user_permissions)) if user_permissions else '无'}"
            )

            # 创建 Agent
            agent = await create_agent_for_session(
                session_id=session_id,
                enable_approval=True,
                enable_security=True,
                user_permissions=user_permissions,
            )

            # 初始化状态
            initial_state: OpsState = {
                "user_id": str(current_user.id),
                "user_role": "admin" if current_user.is_superuser else "user",
                "session_id": session_id,
                "user_input": message_data.content,
                "trigger_source": "web",
                "workflow_status": "running",
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

            # 【调试】增强日志
            logger.info(f"🚀 开始执行 DeepAgents 工作流")
            logger.info(f"   会话ID: {session_id}")
            logger.info(f"   用户输入: {message_data.content[:100]}")
            logger.info(
                f"   初始状态: {json.dumps({k: v for k, v in initial_state.items() if k not in ['collected_data', 'execution_history']}, ensure_ascii=False)}"
            )

            # 发送状态事件：开始处理
            status_data = json.dumps(
                {
                    "type": "status",
                    "status": "processing",
                    "message": "🤖 Agent 正在分析您的请求...",
                },
                ensure_ascii=False,
            )
            yield f"data: {status_data}\n\n"

            # 执行工作流（流式）
            full_response = ""
            workflow_completed = False
            final_state = None

            # 【调试】添加超时检测
            import time

            start_time = time.time()
            timeout = 300  # 5 分钟超时

            async for event in agent.astream(initial_state):
                # 检查超时
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    logger.error(f"⏰ 工作流执行超时: {elapsed:.2f}s")
                    error_data = json.dumps(
                        {"type": "error", "message": f"工作流执行超时（{elapsed:.2f}s）"},
                        ensure_ascii=False,
                    )
                    yield f"data: {error_data}\n\n"
                    break

                event_type = event.get("type")
                logger.info(f"📨 收到事件: type={event_type}, elapsed={elapsed:.2f}s")

                if event_type == "interrupt":
                    # 工作流暂停，需要用户批准
                    interrupt_data = event.get("data", {})
                    approval_message = interrupt_data.get("message", "")
                    commands = interrupt_data.get("commands", [])

                    logger.info(f"⏸️ 工作流暂停，等待用户批准")
                    logger.info(f"批准消息: {approval_message}")

                    # 发送 approval_request 事件给前端
                    approval_data = json.dumps(
                        {
                            "type": "approval_request",
                            "message": approval_message,
                            "commands": commands,
                            "session_id": session_id,
                        },
                        ensure_ascii=False,
                    )
                    yield f"data: {approval_data}\n\n"

                    # 暂时保存部分响应
                    full_response += f"## 📋 命令规划\n\n{approval_message}\n\n"

                    # 工作流暂停，等待用户通过 resume 端点继续
                    # 不发送 done 事件，因为工作流还没完成
                    return

                elif event_type == "node":
                    # 节点执行事件
                    node_name = event.get("node")
                    node_state = event.get("state", {})

                    logger.info(f"📍 节点执行: {node_name}")

                    # 可以根据节点名称发送不同的状态更新
                    if node_name == "intent_analysis":
                        status_msg = "🔍 正在分析意图..."
                    elif node_name == "command_planning":
                        status_msg = "📋 正在规划命令..."
                    elif node_name == "execute_diagnosis":
                        status_msg = "🔧 正在执行诊断..."
                    elif node_name == "analyze_result":
                        status_msg = "📊 正在分析结果..."
                    else:
                        status_msg = f"⚙️ 正在执行: {node_name}"

                    status_data = json.dumps(
                        {"type": "status", "status": "processing", "message": status_msg},
                        ensure_ascii=False,
                    )
                    yield f"data: {status_data}\n\n"

                elif event_type == "complete":
                    # 工作流完成
                    final_state = event.get("state", {})
                    workflow_completed = True

                    logger.info(f"✅ 工作流执行完成")

                    # 构建最终响应
                    final_report = final_state.get("final_report", "")
                    if final_report:
                        full_response += final_report

                        # 发送最终报告
                        chunk_data = json.dumps(
                            {"type": "chunk", "content": final_report}, ensure_ascii=False
                        )
                        yield f"data: {chunk_data}\n\n"
                    else:
                        # 生成状态摘要
                        workflow_status = final_state.get("workflow_status", "unknown")
                        intent_type = final_state.get("intent_type", "unknown")

                        status_msg = f"""## ✅ 工作流执行完成

**意图类型**: {intent_type}
**诊断轮次**: {final_state.get('diagnosis_round', 0)}
**数据充足**: {'是' if final_state.get('data_sufficient') else '否'}
"""
                        full_response += status_msg

                        chunk_data = json.dumps(
                            {"type": "chunk", "content": status_msg}, ensure_ascii=False
                        )
                        yield f"data: {chunk_data}\n\n"

                elif event_type == "error":
                    # 工作流错误
                    error_msg = event.get("error", "未知错误")
                    logger.error(f"❌ 工作流执行失败: {error_msg}")

                    error_data = json.dumps(
                        {"type": "error", "message": f"工作流执行失败: {error_msg}"},
                        ensure_ascii=False,
                    )
                    yield f"data: {error_data}\n\n"
                    return

            # 3. 保存 AI 回复（只有在工作流完成时才保存）
            if workflow_completed and full_response:
                assistant_message = ChatMessage(
                    session_id=session_id,
                    role=MessageRole.ASSISTANT,
                    content=full_response,
                    meta_data=json.dumps(
                        {
                            "workflow_status": (
                                final_state.get("workflow_status") if final_state else "unknown"
                            ),
                            "intent_type": (
                                final_state.get("intent_type") if final_state else "unknown"
                            ),
                            "diagnosis_round": (
                                final_state.get("diagnosis_round", 0) if final_state else 0
                            ),
                        }
                    ),
                )
                db.add(assistant_message)

                # 更新会话
                session.updated_at = datetime.now(timezone.utc)
                if not session.title:
                    session.title = message_data.content[:30] + (
                        "..." if len(message_data.content) > 30 else ""
                    )

                db.commit()
                db.refresh(assistant_message)

                logger.info(
                    f"Assistant message saved: session={session_id}, message_id={assistant_message.id}"
                )

                # 发送完成事件
                done_data = json.dumps(
                    {"type": "done", "message_id": assistant_message.id}, ensure_ascii=False
                )
                yield f"data: {done_data}\n\n"

        except Exception as e:
            logger.error(f"Error in stream generation: {e}", exc_info=True)
            # 发送错误事件
            error_data = json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )


@router.post("/sessions/{session_id}/resume")
async def resume_workflow(
    session_id: str,
    approval_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    恢复暂停的工作流（用户批准后）

    请求体示例:
    {
        "status": "approved"  // 或 "rejected"
    }
    """
    # 验证会话所有权
    # 注意：飞书会话对所有用户可见，Web 会话只对创建者可见
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

    async def generate_resume_stream():
        """生成恢复工作流的 SSE 流式响应"""
        try:
            logger.info(f"▶️ 恢复工作流: session={session_id}, approval={approval_data}")

            # v3.0 架构：直接创建 Agent（单例模式）
            agent = await create_agent_for_session(
                session_id=session_id,
                enable_approval=True,
                enable_security=True,
            )

            # 构造恢复状态（包含批准决定）
            resume_state: OpsState = {
                "session_id": session_id,
                "user_id": str(current_user.id),
                "user_role": "admin" if current_user.is_superuser else "user",
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

            # 【调试】增强日志
            logger.info(f"▶️ 开始恢复 DeepAgents 工作流")
            logger.info(f"   会话ID: {session_id}")
            logger.info(f"   批准决定: {approval_data}")
            logger.info(
                f"   恢复状态: {json.dumps({k: v for k, v in resume_state.items() if k not in ['collected_data', 'execution_history']}, ensure_ascii=False)}"
            )

            # 发送状态事件
            status_data = json.dumps(
                {"type": "status", "status": "resuming", "message": "▶️ 正在恢复工作流..."},
                ensure_ascii=False,
            )
            yield f"data: {status_data}\n\n"

            # 恢复工作流（流式）
            full_response = ""
            workflow_completed = False
            final_state = None

            # 【调试】添加超时检测
            import time

            start_time = time.time()
            timeout = 300  # 5 分钟超时

            async for event in agent.astream(resume_state):
                # 检查超时
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    logger.error(f"⏰ 工作流恢复超时: {elapsed:.2f}s")
                    error_data = json.dumps(
                        {"type": "error", "message": f"工作流恢复超时（{elapsed:.2f}s）"},
                        ensure_ascii=False,
                    )
                    yield f"data: {error_data}\n\n"
                    break

                event_type = event.get("type")
                logger.info(f"📨 收到事件: type={event_type}, elapsed={elapsed:.2f}s")

                if event_type == "interrupt":
                    # 工作流再次暂停（可能有多个批准点）
                    interrupt_data = event.get("data", {})
                    approval_message = interrupt_data.get("message", "")
                    commands = interrupt_data.get("commands", [])

                    logger.info(f"⏸️ 工作流再次暂停")

                    approval_event = json.dumps(
                        {
                            "type": "approval_request",
                            "message": approval_message,
                            "commands": commands,
                            "session_id": session_id,
                        },
                        ensure_ascii=False,
                    )
                    yield f"data: {approval_event}\n\n"

                    full_response += f"\n\n{approval_message}\n\n"
                    return

                elif event_type == "node":
                    # 节点执行事件
                    node_name = event.get("node")
                    logger.info(f"📍 节点执行: {node_name}")

                    # 发送状态更新
                    if node_name == "execute_diagnosis":
                        status_msg = "🔧 正在执行诊断..."
                    elif node_name == "analyze_result":
                        status_msg = "📊 正在分析结果..."
                    elif node_name == "execute_remediation":
                        status_msg = "🔨 正在执行修复..."
                    else:
                        status_msg = f"⚙️ 正在执行: {node_name}"

                    status_data = json.dumps(
                        {"type": "status", "status": "processing", "message": status_msg},
                        ensure_ascii=False,
                    )
                    yield f"data: {status_data}\n\n"

                elif event_type == "complete":
                    # 工作流完成
                    final_state = event.get("state", {})
                    workflow_completed = True

                    logger.info(f"✅ 工作流恢复执行完成")

                    # 构建最终响应
                    final_report = final_state.get("final_report", "")
                    if final_report:
                        full_response += final_report

                        chunk_data = json.dumps(
                            {"type": "chunk", "content": final_report}, ensure_ascii=False
                        )
                        yield f"data: {chunk_data}\n\n"
                    else:
                        status_msg = f"""## ✅ 工作流执行完成

**执行成功**: {'是' if final_state.get('execution_success') else '否'}
"""
                        full_response += status_msg

                        chunk_data = json.dumps(
                            {"type": "chunk", "content": status_msg}, ensure_ascii=False
                        )
                        yield f"data: {chunk_data}\n\n"

                elif event_type == "error":
                    error_msg = event.get("error", "未知错误")
                    logger.error(f"❌ 工作流恢复失败: {error_msg}")

                    error_data = json.dumps(
                        {"type": "error", "message": f"工作流恢复失败: {error_msg}"},
                        ensure_ascii=False,
                    )
                    yield f"data: {error_data}\n\n"
                    return

            # 保存 AI 回复（追加到之前的消息）
            if workflow_completed and full_response:
                # 查找最后一条 assistant 消息
                last_assistant_msg = (
                    db.query(ChatMessage)
                    .filter(
                        ChatMessage.session_id == session_id,
                        ChatMessage.role == MessageRole.ASSISTANT,
                    )
                    .order_by(desc(ChatMessage.created_at))
                    .first()
                )

                if last_assistant_msg:
                    # 追加到现有消息
                    last_assistant_msg.content += f"\n\n{full_response}"
                    last_assistant_msg.meta_data = json.dumps(
                        {
                            "workflow_status": (
                                final_state.get("workflow_status") if final_state else "unknown"
                            ),
                            "execution_success": (
                                final_state.get("execution_success") if final_state else False
                            ),
                        }
                    )
                else:
                    # 创建新消息
                    assistant_message = ChatMessage(
                        session_id=session_id,
                        role=MessageRole.ASSISTANT,
                        content=full_response,
                        meta_data=json.dumps(
                            {
                                "workflow_status": (
                                    final_state.get("workflow_status") if final_state else "unknown"
                                ),
                                "execution_success": (
                                    final_state.get("execution_success") if final_state else False
                                ),
                            }
                        ),
                    )
                    db.add(assistant_message)

                # 更新会话
                session.updated_at = datetime.now(timezone.utc)
                db.commit()

                logger.info(f"Assistant message updated/saved for session={session_id}")

                # 发送完成事件
                done_data = json.dumps({"type": "done"}, ensure_ascii=False)
                yield f"data: {done_data}\n\n"

        except Exception as e:
            logger.error(f"Error in resume stream: {e}", exc_info=True)
            error_data = json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        generate_resume_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
