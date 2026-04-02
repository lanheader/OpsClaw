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
from app.memory.memory_manager import get_memory_manager
from app.services.session_lock_manager import SessionLockContext
from app.utils.logger import get_logger, set_request_context
from app.utils.llm_helper import ensure_final_report_in_state

logger = get_logger(__name__)

# 常量
AGENT_TIMEOUT = 120  # 2 分钟（整体执行超时）
LLM_CALL_TIMEOUT = 120  # 单次 LLM 调用超时（秒）


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
    if not isinstance(node_state, dict):
        return None

    try:
        result = {}

        # 始终保留原始 node_state 的引用，供后续提取
        result["_raw_node_state"] = node_state

        if "messages" in node_state:
            result["messages"] = [
                {"type": type(m).__name__, "content": getattr(m, 'content', str(m))}
                for m in node_state.get("messages", [])
            ]
        else:
            result["raw_state"] = True

        # 始终提取这些字段
        for key in ("formatted_response", "final_report", "response", "output", "reply"):
            if key in node_state:
                result[key] = node_state[key]

        result["intent_type"] = node_state.get("intent_type", "unknown")
        result["diagnosis_round"] = node_state.get("diagnosis_round", 0)
        return result
    except Exception:
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
        for node_name, node_state in event.items():
            if node_name.startswith("__"):
                continue

            status_msg = _get_status_message(node_name)
            state_update = _extract_state_from_node(node_state)

            return (
                EventType.STATUS,
                {"status": "processing", "message": status_msg},
                state_update
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


async def _inject_memory(text: str, session_id: str, user_id: int) -> str:
    """记忆注入"""
    try:
        memory_manager = get_memory_manager(user_id=str(user_id))
        context_str = await memory_manager.build_context(
            user_query=text,
            session_id=session_id,
            include_incidents=True,
            include_knowledge=True,
            include_session=True,
            include_summary=True,
            max_tokens=4500,
        )
        if context_str:
            enhanced = (
                f"{text}\n\n---\n**参考资料**（来自历史对话和知识库）：\n"
                f"{context_str}\n---"
            )
            logger.info(f"🧠 记忆已注入: {len(context_str)} 字符")
            return enhanced
    except Exception as e:
        logger.warning(f"⚠️ 记忆注入失败: {e}")

    return text


def _extract_reply(final_state: Dict[str, Any], workflow_completed: bool) -> Optional[str]:
    """提取最终回复（统一清理 XML 标签）"""
    try:
        if final_state:
            try:
                final_state = ensure_final_report_in_state(final_state)
            except Exception as e:
                logger.warning(f"⚠️ ensure_final_report_in_state 失败: {e}")

            # 按优先级提取回复
            for key in ["formatted_response", "final_report", "final_answer", "response"]:
                reply = final_state.get(key, "")
                if reply:
                    logger.info(f"📝 从 final_state 提取到回复 (key={key}, 长度: {len(reply)})")
                    return _clean_reply(reply)

            # 从 messages 中提取
            messages = final_state.get("messages", [])
            if messages:
                for msg in reversed(messages):
                    if isinstance(msg, dict):
                        msg_type = msg.get("type", "")
                        content = msg.get("content", "")
                        # 匹配 "ai", "AIMessage", "AIMessageChunk" 等
                        if ("ai" in str(msg_type).lower()) and content:
                            logger.info(f"📝 从 messages 提取到回复 (type={msg_type}, 长度: {len(content)})")
                            return _clean_reply(content)
                    elif hasattr(msg, 'type'):
                        # langchain Message 对象
                        if 'ai' in str(msg.type).lower():
                            content = getattr(msg, 'content', None) or ""
                            if content:
                                logger.info(f"📝 从 messages 提取到回复 (AIMessage obj, 长度: {len(content)})")
                                return _clean_reply(content)

            # 调试：打印 final_state keys 和 messages 结构
            logger.warning(f"⚠️ 未能从 final_state 提取回复. keys={list(final_state.keys())}, messages_count={len(messages) if messages else 0}")
            if messages and len(messages) > 0:
                last_msg = messages[-1]
                if isinstance(last_msg, dict):
                    logger.warning(f"  最后一条消息: type={last_msg.get('type')}, has_content={bool(last_msg.get('content'))}")
                else:
                    logger.warning(f"  最后一条消息: class={type(last_msg).__name__}, type={getattr(last_msg, 'type', None)}, content={getattr(last_msg, 'content', None)[:100] if getattr(last_msg, 'content', None) else None}")

            # 兜底1：从 _raw_node_state 的 messages 里提取（langchain Message 对象）
            raw_state = final_state.get("_raw_node_state")
            if isinstance(raw_state, dict) and "messages" in raw_state:
                for msg in reversed(raw_state["messages"]):
                    content = None
                    if isinstance(msg, dict):
                        content = msg.get("content", "")
                    elif hasattr(msg, "content"):
                        content = msg.content
                    if content and isinstance(content, str) and len(content) > 5:
                        logger.info(f"📝 从 _raw_node_state.messages 提取到回复 (长度: {len(content)})")
                        return _clean_reply(content)

            # 兜底2：遍历所有字段，找到第一个看起来像回复的字符串
            for key, val in final_state.items():
                if key in ("raw_state", "workflow_status", "intent_type", "diagnosis_round"):
                    continue
                if isinstance(val, str) and len(val) > 10 and not val.startswith("{"):
                    logger.info(f"📝 兜底从 final_state['{key}'] 提取回复 (长度: {len(val)})")
                    return _clean_reply(val)

    except Exception as e:
        logger.error(f"❌ 提取回复失败: {e}")

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
) -> AsyncGenerator[Tuple[EventType, Dict, Optional[Dict]], None]:
    """
    执行 Agent 并流式返回事件

    Yields:
        (event_type, event_data, state_update)
    """
    start_time = time.time()

    async for event in agent.astream(input_state, config=config):
        # 超时检查
        elapsed = time.time() - start_time
        if elapsed > timeout:
            yield EventType.ERROR, {"message": f"处理超时（{elapsed:.0f}s）"}, None
            return

        # 处理事件
        result = _process_event(event, session_id)
        if result:
            yield result


class AgentChatService:
    """
    Agent 聊天服务 - 统一的消息处理核心

    提供两种调用方式：
    1. 流式模式：process_message_stream() - 用于 Web SSE
    2. 非流式模式：process_message() - 用于飞书等
    """

    def __init__(self):
        self.settings = get_settings()

    async def process_message_stream(
        self,
        request: ChatRequest,
    ) -> AsyncGenerator[StreamEvent, None]:
        """流式处理消息（用于 Web SSE）"""
        logger.info(
            f"🚀 [AgentChatService] 开始流式处理: "
            f"session={request.session_id}, channel={request.channel.value}"
        )

        final_state: Dict[str, Any] = {}
        workflow_completed = False
        full_response = ""

        try:
            # 发送处理中状态
            yield StreamEvent(
                type=EventType.STATUS,
                data={"status": "processing", "message": "🤖 Agent 正在分析您的请求..."}
            )

            # 使用会话锁保护处理过程
            async with SessionLockContext(request.session_id, timeout=AGENT_TIMEOUT):
                logger.info(f"🔒 获取会话锁成功: {request.session_id}")

                # 准备并执行
                agent, input_state, config = await self._prepare_agent(request)

                # 使用 asyncio.timeout 保护整体执行时间
                try:
                    async with asyncio.timeout(AGENT_TIMEOUT):
                        async for event_type, event_data, state_update in _execute_agent_stream(
                            agent, input_state, config, request.session_id
                        ):
                            # 发送状态更新
                            if event_type == EventType.STATUS:
                                yield StreamEvent(type=EventType.STATUS, data=event_data)

                            # 处理审批中断
                            elif event_type == EventType.APPROVAL_REQUEST:
                                yield StreamEvent(type=EventType.APPROVAL_REQUEST, data=event_data)
                                return

                            # 更新 final_state
                            if state_update:
                                final_state.update(state_update)
                                workflow_completed = True
                except asyncio.TimeoutError:
                    logger.error(f"⏰ Agent 执行超时: session={request.session_id}")
                    yield StreamEvent(
                        type=EventType.ERROR,
                        data={"message": f"Agent 执行超时（{AGENT_TIMEOUT}s），请稍后重试"}
                    )
                    return

                # 提取最终回复
                full_response = _extract_reply(final_state, workflow_completed) or ""

            logger.info(f"🔓 释放会话锁: {request.session_id}")

            # 发送回复
            if full_response:
                yield StreamEvent(type=EventType.CHUNK, data={"content": full_response})
                yield StreamEvent(
                    type=EventType.DONE,
                    data={
                        "message_id": None,
                        "final_state": final_state,
                        "workflow_completed": workflow_completed
                    }
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
                    async for event_type, event_data, state_update in _execute_agent_stream(
                        agent, input_state, config, request.session_id
                    ):
                        # 处理审批中断
                        if event_type == EventType.APPROVAL_REQUEST:
                            return ChatResponse(
                            reply=event_data.get("message", "等待审批"),
                            session_id=request.session_id,
                            workflow_status="awaiting_approval",
                            needs_approval=True,
                            approval_data=event_data
                        )

                    # 更新 final_state
                    if state_update:
                        final_state.update(state_update)
                        workflow_completed = True
            except asyncio.TimeoutError:
                logger.error(f"⏰ Agent 执行超时: session={request.session_id}")
                return ChatResponse(
                    reply=f"⚠️ Agent 执行超时（{AGENT_TIMEOUT}s），请稍后重试。",
                    session_id=request.session_id,
                    workflow_status="error"
                )

            # 提取最终回复
            reply = _extract_reply(final_state, workflow_completed)

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
        agent = await create_agent_for_session(
            session_id=request.session_id,
            enable_approval=True,
            enable_security=request.enable_security,
            user_permissions=request.user_permissions,
            user_id=request.user_id,
        )

        # 记忆注入
        enhanced_text = await _inject_memory(
            request.content, request.session_id, request.user_id
        )

        # 构建输入状态和配置
        input_state = {"messages": [HumanMessage(content=enhanced_text)]}
        config = get_thread_config(request.session_id)

        return agent, input_state, config


_agent_chat_service: Optional[AgentChatService] = None


def get_agent_chat_service() -> AgentChatService:
    """获取 AgentChatService 单例"""
    global _agent_chat_service
    if _agent_chat_service is None:
        _agent_chat_service = AgentChatService()
    return _agent_chat_service
