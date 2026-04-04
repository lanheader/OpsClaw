"""
Agent 聊天服务 - 统一的消息处理服务

职责：
- 统一处理 Web 和飞书的 Agent 调用
- 统一的状态提取和回复生成
- 统一的消息保存和自动学习
- 支持流式和非流式两种模式

使用方式：
    # 流式模式（Web SSE）
    async for event in agent_chat_service.process_message_stream(...):
        yield event

    # 非流式模式（飞书）
    result = await agent_chat_service.process_message(...)
    reply = result.reply
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncGenerator, Dict, Any, Optional, List, Tuple

from langchain_core.messages import AIMessage, HumanMessage

from app.core.config import get_settings
from app.deepagents.factory import create_agent_for_session
from app.deepagents.main_agent import get_thread_config
from app.services.session_lock_manager import SessionLockContext
from app.utils.logger import get_logger, set_request_context
from app.utils.llm_helper import ensure_final_report_in_state

logger = get_logger(__name__)

# 常量
AGENT_TIMEOUT = 1200  # 20 分钟（整体执行超时）
LLM_CALL_TIMEOUT = 600  # 单次 LLM 调用超时（10分钟）


# ========== 数据模型 ==========

class MessageChannel(Enum):
    """消息渠道"""
    WEB = "web"
    FEISHU = "feishu"


class EventType(Enum):
    """事件类型（用于流式响应）"""
    STATUS = "status"
    CHUNK = "chunk"
    APPROVAL_REQUEST = "approval_request"
    DONE = "done"
    ERROR = "error"


@dataclass
class ChatRequest:
    """聊天请求"""
    session_id: str
    user_id: int
    content: str
    channel: MessageChannel
    user_permissions: List[str] = field(default_factory=list)
    chat_id: Optional[str] = None
    enable_security: bool = True


@dataclass
class ChatResponse:
    """聊天响应"""
    reply: str
    session_id: str
    message_id: Optional[int] = None
    workflow_status: str = "completed"
    intent_type: str = "unknown"
    diagnosis_round: int = 0
    needs_approval: bool = False
    approval_data: Optional[Dict[str, Any]] = None
    final_state: Optional[Dict[str, Any]] = None


@dataclass
class StreamEvent:
    """流式事件"""
    type: EventType
    data: Dict[str, Any]


def _get_status_message(node_name: str) -> str:
    """根据节点名获取状态消息"""
    status_map = {
        "intent_analysis": "🔍 正在分析意图...",
        "command_planning": "📋 正在规划命令...",
        "execute_diagnosis": "🔧 正在执行诊断...",
        "analyze_result": "📊 正在分析结果...",
    }
    return status_map.get(node_name, f"⚙️ 正在执行: {node_name}")


def _extract_approval_info(interrupt_data: Any) -> Optional[Dict[str, Any]]:
    """从 interrupt 数据中提取审批信息"""
    try:
        if isinstance(interrupt_data, tuple) and len(interrupt_data) > 0:
            interrupt_obj = interrupt_data[0]
            if hasattr(interrupt_obj, 'value'):
                approval_info = interrupt_obj.value
                action_requests = approval_info.get('action_requests', [])

                # 转换为统一格式
                commands = [
                    {
                        'type': _infer_tool_type(req.get('name', '')),
                        'action': req.get('name', 'unknown'),
                        'params': req.get('args', {}),
                        'reason': req.get('description', '')
                    }
                    for req in action_requests
                ]

                return {
                    "message": f"需要执行 {len(commands)} 个操作",
                    "commands": commands,
                    "action_requests": action_requests,
                    "review_configs": approval_info.get('review_configs', [])
                }

        elif isinstance(interrupt_data, dict):
            return {
                "message": interrupt_data.get("message", "等待审批"),
                "commands": interrupt_data.get("commands", []),
            }

    except Exception as e:
        logger.warning(f"⚠️ 提取审批信息失败: {e}")

    return None


def _infer_tool_type(tool_name: str) -> str:
    """推断工具类型"""
    if tool_name.startswith('delete_') or tool_name.startswith('restart_'):
        return 'k8s'
    elif 'prometheus' in tool_name.lower():
        return 'prometheus'
    return 'k8s'


def _extract_state_from_node(node_state: Any) -> Optional[Dict]:
    """从节点状态中提取信息"""
    try:
        # 如果不是 dict，尝试转换为 dict（LangGraph 可能返回 StateSnapshot 等对象）
        if not isinstance(node_state, dict):
            if hasattr(node_state, 'values'):
                node_state = node_state.values
            elif hasattr(node_state, '__dict__'):
                node_state = vars(node_state)
            else:
                logger.warning(f"⚠️ _extract_state_from_node: 不支持的状态类型 {type(node_state).__name__}: {repr(node_state)[:200]}")
                return None

        if not isinstance(node_state, dict):
            return None

        result = {}

        # 始终保留原始 node_state 的引用，供后续提取
        result["_raw_node_state"] = node_state

        # 安全获取字段（避免 LangGraph Overwrite 对象的迭代问题）
        def _safe_get(d, key, default=None):  # type: ignore[no-untyped-def]
            try:
                return d[key] if key in d else default
            except TypeError:
                return default

        def _safe_has(d, key):  # type: ignore[no-untyped-def]
            try:
                return key in d
            except TypeError:
                return False

        messages = _safe_get(node_state, "messages")
        if messages is not None:
            try:
                result["messages"] = [  # type: ignore[assignment]
                    {"type": type(m).__name__, "content": getattr(m, 'content', str(m))}
                    for m in messages
                ]
            except TypeError:
                result["raw_state"] = True  # type: ignore[assignment]
        else:
            result["raw_state"] = True  # type: ignore[assignment]

        # 始终提取这些字段
        for key in ("formatted_response", "final_report", "response", "output", "reply"):
            val = _safe_get(node_state, key)
            if val is not None:
                result[key] = val

        result["intent_type"] = _safe_get(node_state, "intent_type", "unknown")
        result["diagnosis_round"] = _safe_get(node_state, "diagnosis_round", 0)
        return result
    except Exception as e:
        logger.warning(f"⚠️ _extract_state_from_node 异常: {e}")
        return {"raw_state": True}


def _process_event(
    event: Dict[str, Any],
    session_id: str,
) -> Optional[Tuple[EventType, Dict[str, Any], Optional[Dict]]]:
    """
    处理单个事件

    Returns:
        (event_type, event_data, state_update) 或 None
    """
    if not isinstance(event, dict):
        return None

    # 1. 处理 interrupt 事件（审批流程）
    if "__interrupt__" in event:
        interrupt_data = event["__interrupt__"]
        approval_info = _extract_approval_info(interrupt_data)

        if approval_info:
            # 保存审批状态
            try:
                from app.services.session_state_manager import SessionStateManager
                SessionStateManager.set_awaiting_approval(
                    session_id, approval_data=approval_info
                )
            except Exception as e:
                logger.warning(f"⚠️ 保存审批状态失败: {e}")

            return (
                EventType.APPROVAL_REQUEST,
                {
                    "message": approval_info.get("message", "等待审批"),
                    "commands": approval_info.get("commands", []),
                    "session_id": session_id,
                    "action_requests": approval_info.get("action_requests", []),
                },
                None
            )

    # 2. 处理节点事件
    event_type = event.get("type")
    if event_type is None:
        # LangGraph 节点事件格式: {node_name: state}
        try:
            items = list(event.items())
        except TypeError:
            logger.warning(f"⚠️ _process_event: event.items() 失败, type={type(event).__name__}")
            return None

        for node_name, node_state in items:
            if not isinstance(node_name, str) or node_name.startswith("__"):
                continue

            status_msg = _get_status_message(node_name)
            state_update = _extract_state_from_node(node_state)

            return (  # type: ignore[return-value]
                EventType.STATUS,
                {"status": "processing", "message": status_msg},
                state_update,
                node_state  # 额外返回原始 node_state
            )

    # 3. 处理自定义 complete 事件
    if event_type == "complete":
        return (
            EventType.STATUS,
            {"status": "completed", "message": "✅ 处理完成"},
            event.get("state", {})
        )

    # 4. 处理自定义 interrupt 事件（兼容旧格式）
    if event_type == "interrupt":
        interrupt_data = event.get("data", {})
        return (
            EventType.APPROVAL_REQUEST,
            {
                "message": interrupt_data.get("message", "等待审批"),
                "commands": interrupt_data.get("commands", []),
                "session_id": session_id,
            },
            None
        )

    # 5. 处理 error 事件
    if event_type == "error":
        return (
            EventType.ERROR,
            {"message": event.get("error", "未知错误")},
            None
        )

    return None


def _extract_reply(final_state: Dict[str, Any], workflow_completed: bool) -> Optional[str]:
    """
    提取最终回复（按 DeepAgents 官方推荐方式）

    优先级：
    1. 从 messages 列表提取最后一条 AI 消息（最可靠）
    2. 从特定字段提取（兜底）

    Args:
        final_state: 累积的最终状态
        workflow_completed: 工作流是否完成

    Returns:
        清理后的回复文本，或 None
    """
    try:
        if not final_state:
            return None

        # 方法 1：从 messages 列表提取（推荐）
        messages = final_state.get("messages", [])
        if messages:
            for msg in reversed(messages):
                content = None

                # 处理 dict 格式
                if isinstance(msg, dict):
                    msg_type = msg.get("type", "")
                    if "ai" in str(msg_type).lower():
                        content = msg.get("content", "")

                # 处理 LangChain Message 对象
                elif hasattr(msg, 'type') and 'ai' in str(msg.type).lower():
                    # 优先使用 text 属性，兜底使用 content
                    content = getattr(msg, 'text', None) or getattr(msg, 'content', None)

                # 验证内容有效性
                if content and isinstance(content, str):
                    # 跳过包含工具调用标签的中间状态
                    if "<tool_code>" in content or "<tool_name>" in content:
                        logger.debug(f"⏭️ 跳过中间状态 (含工具调用标签)")
                        continue

                    logger.info(f"📝 从 messages 提取到回复 (长度: {len(content)})")
                    return _clean_reply(content)

        # 方法 2：从特定字段提取（兜底）
        for key in ["formatted_response", "final_report", "final_answer", "response"]:
            reply = final_state.get(key, "")
            if reply and isinstance(reply, str):
                # 跳过包含工具调用标签的中间状态
                if "<tool_code>" in reply or "<tool_name>" in reply:
                    logger.debug(f"⏭️ 跳过字段 {key} (含工具调用标签)")
                    continue

                logger.info(f"📝 从字段 {key} 提取到回复 (长度: {len(reply)})")
                return _clean_reply(reply)

        # 未找到有效回复
        logger.warning(
            f"⚠️ 未能提取回复 | "
            f"keys={list(final_state.keys())}, "
            f"messages_count={len(messages) if messages else 0}"
        )

    except Exception as e:
        logger.error(f"❌ 提取回复失败: {e}")

    # 兜底消息
    if workflow_completed:
        return "✅ 任务已完成，但没有生成文本回复。"

    return None


def _clean_reply(content: str) -> str:
    """统一清理回复内容（XML 标签等），所有渠道共用"""
    try:
        from app.integrations.feishu.message_formatter import clean_xml_tags
        return clean_xml_tags(content)
    except Exception:
        return content


async def _execute_agent_stream(
    agent: Any,
    input_state: Dict,
    config: Dict,
    session_id: str,
    timeout: int = AGENT_TIMEOUT,
) -> AsyncGenerator[Tuple[EventType, Dict, Optional[Dict], Optional[Any]], None]:
    """
    执行 Agent 并流式返回事件（使用 DeepAgents v2 格式）

    Yields:
        (event_type, event_data, state_update, raw_node_state)
    """
    start_time = time.time()

    async for chunk in agent.astream(
        input_state,
        config=config,
        stream_mode="updates",  # v2: 明确指定模式
        version="v2",           # v2: 使用统一事件格式
        subgraphs=True,         # v2: 启用子智能体事件
    ):
        # 超时检查
        elapsed = time.time() - start_time
        if elapsed > timeout:
            yield EventType.ERROR, {"message": f"处理超时（{elapsed:.0f}s）"}, None, None  # type: ignore[misc]
            return

        # 1. 处理审批中断
        if "__interrupt__" in chunk:
            interrupt_data = chunk["__interrupt__"]
            approval_info = _extract_approval_info(interrupt_data)
            if approval_info:
                try:
                    from app.services.session_state_manager import SessionStateManager
                    SessionStateManager.set_awaiting_approval(
                        session_id, approval_data=approval_info
                    )
                except Exception as e:
                    logger.warning(f"⚠️ 保存审批状态失败: {e}")

                yield (  # type: ignore[misc]
                    EventType.APPROVAL_REQUEST,
                    {
                        "message": approval_info.get("message", "等待审批"),
                        "commands": approval_info.get("commands", []),
                        "session_id": session_id,
                        "action_requests": approval_info.get("action_requests", []),
                    },
                    None,
                    None,
                )
            continue

        # 2. 处理 updates 事件（节点状态更新）
        chunk_type = chunk.get("type") if isinstance(chunk, dict) else None
        if chunk_type == "updates":
            chunk_data = chunk.get("data", {})
            for node_name, node_state in chunk_data.items():
                # 跳过中间件事件和内部节点
                if "Middleware" in node_name or node_name.startswith("__"):
                    logger.debug(f"⏭️ 跳过中间件/内部节点事件: {node_name}")
                    continue

                status_msg = _get_status_message(node_name)
                state_update = _extract_state_from_node(node_state)

                logger.info(f"📍 节点 {node_name} 执行完成")

                yield (  # type: ignore[misc]
                    EventType.STATUS,
                    {"status": "processing", "message": status_msg},
                    state_update,
                    node_state,
                )

        # 3. 处理 error 事件
        elif chunk_type == "error":
            yield (  # type: ignore[misc]
                EventType.ERROR,
                {"message": chunk.get("error", "未知错误")},
                None,
                None,
            )


class AgentChatService:
    """
    Agent 聊天服务 - 统一的消息处理核心

    提供两种调用方式：
    1. 流式模式：process_message_stream() - 用于 Web SSE
    2. 非流式模式：process_message() - 用于飞书等
    """

    def __init__(self):  # type: ignore[no-untyped-def]
        self.settings = get_settings()

    async def process_message_stream(
        self,
        request: ChatRequest,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        流式处理消息（用于 Web SSE）

        使用 DeepAgents 官方 v2 组合模式：
        - stream_mode=["updates", "messages"]
        - updates: 追踪节点状态、检测审批中断
        - messages: 实时 token 流式输出（主智能体，ns=()）
        """
        logger.info(
            f"🚀 [AgentChatService] 开始流式处理: "
            f"session={request.session_id}, channel={request.channel.value}"
        )

        final_state: Dict[str, Any] = {}
        workflow_completed = False
        streamed_content = ""

        try:
            yield StreamEvent(
                type=EventType.STATUS,
                data={"status": "processing", "message": "🤖 Agent 正在分析您的请求..."}
            )

            async with SessionLockContext(request.session_id, timeout=AGENT_TIMEOUT):
                logger.info(f"🔒 获取会话锁成功: {request.session_id}")

                agent, input_state, config = await self._prepare_agent(request)

                try:
                    async with asyncio.timeout(AGENT_TIMEOUT):
                        async for chunk in agent.astream(
                            input_state,
                            config=config,
                            stream_mode=["updates", "messages"],  # 官方组合模式
                            version="v2",
                            subgraphs=True,
                        ):
                            chunk_type = chunk.get("type") if isinstance(chunk, dict) else None

                            # 1. 检测审批中断
                            if "__interrupt__" in chunk:
                                interrupt_data = chunk["__interrupt__"]
                                approval_info = _extract_approval_info(interrupt_data)
                                if approval_info:
                                    try:
                                        from app.services.session_state_manager import SessionStateManager
                                        SessionStateManager.set_awaiting_approval(
                                            session_id=request.session_id,
                                            approval_data=approval_info,
                                        )
                                    except Exception as e:
                                        logger.warning(f"⚠️ 保存审批状态失败: {e}")
                                    yield StreamEvent(
                                        type=EventType.APPROVAL_REQUEST,
                                        data={
                                            "message": approval_info.get("message", "等待审批"),
                                            "commands": approval_info.get("commands", []),
                                            "session_id": request.session_id,
                                            "action_requests": approval_info.get("action_requests", []),
                                        },
                                    )
                                    return

                            # 2. updates 事件：追踪节点状态
                            elif chunk_type == "updates":
                                for node_name, node_state in chunk.get("data", {}).items():
                                    if "Middleware" in node_name or node_name.startswith("__"):
                                        logger.debug(f"⏭️ 跳过中间件节点: {node_name}")
                                        continue
                                    logger.info(f"📍 节点 {node_name} 执行完成")
                                    yield StreamEvent(
                                        type=EventType.STATUS,
                                        data={"status": "processing", "message": _get_status_message(node_name)},
                                    )
                                    state_update = _extract_state_from_node(node_state)
                                    if state_update:
                                        final_state.update(state_update)
                                        workflow_completed = True

                            # 3. messages 事件：实时 token 流式输出（官方推荐）
                            elif chunk_type == "messages":
                                ns = chunk.get("ns", ())
                                # 只流式输出主智能体的内容（ns 为空元组表示主智能体）
                                if not ns:
                                    message_chunk, _metadata = chunk["data"]
                                    content = getattr(message_chunk, "content", "") or ""
                                    # 跳过包含工具调用标签的中间状态
                                    if content and "<tool_code>" not in content and "<tool_name>" not in content:
                                        streamed_content += content
                                        yield StreamEvent(
                                            type=EventType.CHUNK,
                                            data={"content": content},
                                        )

                except asyncio.TimeoutError:
                    logger.error(f"⏰ Agent 执行超时: session={request.session_id}")
                    yield StreamEvent(
                        type=EventType.ERROR,
                        data={"message": f"Agent 执行超时（{AGENT_TIMEOUT}s），请稍后重试"},
                    )
                    return

            logger.info(f"🔓 释放会话锁: {request.session_id}")

            # 如果 messages 流式已输出内容，直接 DONE
            if streamed_content:
                yield StreamEvent(
                    type=EventType.DONE,
                    data={
                        "message_id": None,
                        "final_state": final_state,
                        "workflow_completed": workflow_completed,
                    },
                )
            else:
                # messages 流式无内容时，从 final_state 提取（兜底）
                full_response = _extract_reply(final_state, workflow_completed) or ""
                if full_response:
                    yield StreamEvent(type=EventType.CHUNK, data={"content": full_response})
                    yield StreamEvent(
                        type=EventType.DONE,
                        data={
                            "message_id": None,
                            "final_state": final_state,
                            "workflow_completed": workflow_completed,
                        },
                    )
                else:
                    yield StreamEvent(type=EventType.ERROR, data={"message": "未能生成有效回复"})

        except Exception as e:
            logger.exception(f"❌ 流式处理失败: {e}")
            yield StreamEvent(type=EventType.ERROR, data={"message": str(e)})

    async def process_message(self, request: ChatRequest) -> ChatResponse:
        """
        非流式处理消息（用于飞书等）

        注意：调用者（如 agent_invoker）应该已经获取了会话锁，
        这里不再重复获取锁，避免死锁。
        """
        logger.info(
            f"🚀 [AgentChatService] 开始非流式处理: "
            f"session={request.session_id}, channel={request.channel.value}"
        )

        final_state: Dict[str, Any] = {}
        workflow_completed = False

        try:
            # 注意：会话锁由调用者（agent_invoker）管理，这里不重复获取

            # 准备并执行
            agent, input_state, config = await self._prepare_agent(request)

            try:
                async with asyncio.timeout(AGENT_TIMEOUT):
                    async for event in _execute_agent_stream(
                        agent, input_state, config, request.session_id
                    ):
                        # event 是元组：(event_type, event_data, state_update, raw_node_state)
                        if not isinstance(event, tuple) or len(event) < 3:
                            continue
                        event_type, event_data, state_update = event[0], event[1], event[2]
                        raw_node_state = event[3] if len(event) > 3 else None

                        # 处理审批中断
                        if event_type == EventType.APPROVAL_REQUEST:
                            return ChatResponse(
                                reply=event_data.get("message", "等待审批"),
                                session_id=request.session_id,
                                workflow_status="awaiting_approval",
                                needs_approval=True,
                                approval_data=event_data
                            )

                        # 收集有效状态
                        if state_update:
                            final_state.update(state_update)
                            workflow_completed = True

                        # 如果 state_update 为空但有原始节点状态，直接尝试提取
                        if not state_update and raw_node_state is not None:
                            extracted = _extract_state_from_node(raw_node_state)
                            if extracted and not extracted.get("raw_state"):
                                final_state.update(extracted)
                                workflow_completed = True
            except asyncio.TimeoutError:
                logger.error(f"⏰ Agent 执行超时: session={request.session_id}")
                return ChatResponse(
                    reply=f"⚠️ Agent 执行超时（{AGENT_TIMEOUT}s），请稍后重试。",
                    session_id=request.session_id,
                    workflow_status="error"
                )

            # 终极兜底：如果 astream 没拿到任何有效状态，直接 ainvoke
            if not final_state:
                logger.info(f"📝 astream 未提取到状态，回退到 ainvoke: session={request.session_id}")
                try:
                    result = await agent.ainvoke(input_state, config=config)
                    if isinstance(result, dict):
                        final_state = result
                        workflow_completed = True
                        logger.info(f"✅ ainvoke 成功，keys={list(result.keys())[:5]}")
                except Exception as e:
                    logger.warning(f"⚠️ ainvoke 回退失败: {e}")

            # 提取最终回复
            reply = _extract_reply(final_state, workflow_completed)

            logger.info(f"🔍 final_state keys={list(final_state.keys())}, reply_len={len(reply) if reply else 0}")

            return ChatResponse(
                reply=reply or "未能生成有效回复",
                session_id=request.session_id,
                workflow_status="completed" if workflow_completed else "interrupted",
                final_state=final_state,
                intent_type=final_state.get("intent_type", "unknown") if final_state else "unknown",
                diagnosis_round=final_state.get("diagnosis_round", 0) if final_state else 0,
            )

        except Exception as e:
            logger.exception(f"❌ 非流式处理失败: {e}")
            return ChatResponse(
                reply=f"处理失败: {str(e)}",
                session_id=request.session_id,
                workflow_status="error"
            )

    async def _prepare_agent(
        self,
        request: ChatRequest,
    ) -> Tuple[Any, Dict, Dict]:
        """准备 Agent、输入状态和配置"""
        # 设置请求上下文（用于中间件读取权限）
        set_request_context(
            session_id=request.session_id,
            user_id=str(request.user_id),
            user_permissions=request.user_permissions,
        )
        logger.info(
            f"🔐 已设置请求上下文: session_id={request.session_id}, "
            f"user_id={request.user_id}, permissions={request.user_permissions}"
        )

        # 获取 Agent
        agent = await create_agent_for_session(  # type: ignore[call-arg]
            session_id=request.session_id,
            enable_approval=True,
            enable_security=request.enable_security,
            user_permissions=request.user_permissions,  # type: ignore[arg-type]
            user_id=request.user_id,
        )

        # 构建输入状态和配置
        input_state = {"messages": [HumanMessage(content=request.content)]}
        config = get_thread_config(request.session_id)

        return agent, input_state, config


_agent_chat_service: Optional[AgentChatService] = None


def get_agent_chat_service() -> AgentChatService:
    """获取 AgentChatService 单例"""
    global _agent_chat_service
    if _agent_chat_service is None:
        _agent_chat_service = AgentChatService()
    return _agent_chat_service
