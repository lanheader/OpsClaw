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

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import AsyncGenerator, Dict, Any, Optional, List, Callable, Awaitable

from langchain_core.messages import AIMessage, HumanMessage

from app.utils.logger import get_logger
from app.core.config import get_settings
from app.deepagents.factory import create_agent_for_session
from app.deepagents.main_agent import get_thread_config
from app.utils.llm_helper import ensure_final_report_in_state
from app.memory.memory_manager import get_memory_manager

logger = get_logger(__name__)

# 常量
AGENT_TIMEOUT = 300  # 5 分钟
MAX_RETRY = 1
_FAILURE_MARKERS = ["工具调用失败", "执行失败", "无法完成", "❌ 任务失败"]


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
    chat_id: Optional[str] = None  # 飞书需要
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
        """
        流式处理消息（用于 Web SSE）

        Args:
            request: 聊天请求

        Yields:
            StreamEvent: 流式事件
        """
        logger.info(
            f"🚀 [AgentChatService] 开始流式处理: "
            f"session={request.session_id}, channel={request.channel.value}"
        )

        final_state: Dict[str, Any] = {}
        workflow_completed = False
        full_response = ""

        try:
            # 1. 发送处理中状态
            yield StreamEvent(
                type=EventType.STATUS,
                data={
                    "status": "processing",
                    "message": "🤖 Agent 正在分析您的请求..."
                }
            )

            # 2. 获取 Agent
            agent = await create_agent_for_session(
                session_id=request.session_id,
                enable_approval=True,
                enable_security=request.enable_security,
                user_permissions=request.user_permissions,
                user_id=request.user_id,
            )

            # 3. 记忆注入
            enhanced_text = await self._inject_memory(
                request.content, request.session_id, request.user_id
            )

            # 4. 构建输入状态
            input_state = {"messages": [HumanMessage(content=enhanced_text)]}
            config = get_thread_config(request.session_id)

            # 5. 流式执行
            start_time = time.time()

            async for event in agent.astream(input_state, config=config):
                # 超时检查
                elapsed = time.time() - start_time
                if elapsed > AGENT_TIMEOUT:
                    yield StreamEvent(
                        type=EventType.ERROR,
                        data={"message": f"处理超时（{elapsed:.0f}s）"}
                    )
                    return

                # 处理事件
                event_result = self._process_event(event, request.session_id)
                if event_result:
                    event_type, event_data, state_update = event_result

                    # 发送状态更新
                    if event_type == EventType.STATUS:
                        yield StreamEvent(type=EventType.STATUS, data=event_data)

                    # 处理审批中断
                    elif event_type == EventType.APPROVAL_REQUEST:
                        yield StreamEvent(
                            type=EventType.APPROVAL_REQUEST,
                            data=event_data
                        )
                        return  # 等待用户审批

                    # 更新 final_state
                    if state_update:
                        final_state.update(state_update)
                        workflow_completed = True

            # 6. 提取最终回复
            full_response = await self._extract_reply(final_state, workflow_completed)

            if full_response:
                # 发送回复内容
                yield StreamEvent(
                    type=EventType.CHUNK,
                    data={"content": full_response}
                )

                # 发送完成事件（包含 final_state 供外部保存）
                yield StreamEvent(
                    type=EventType.DONE,
                    data={
                        "message_id": None,
                        "final_state": final_state,
                        "workflow_completed": workflow_completed
                    }
                )
            else:
                yield StreamEvent(
                    type=EventType.ERROR,
                    data={"message": "未能生成有效回复"}
                )

        except Exception as e:
            logger.exception(f"❌ 流式处理失败: {e}")
            yield StreamEvent(
                type=EventType.ERROR,
                data={"message": str(e)}
            )

    async def process_message(
        self,
        request: ChatRequest,
    ) -> ChatResponse:
        """
        非流式处理消息（用于飞书等）

        Args:
            request: 聊天请求

        Returns:
            ChatResponse: 聊天响应
        """
        logger.info(
            f"🚀 [AgentChatService] 开始非流式处理: "
            f"session={request.session_id}, channel={request.channel.value}"
        )

        final_state: Dict[str, Any] = {}
        workflow_completed = False

        try:
            # 1. 获取 Agent
            agent = await create_agent_for_session(
                session_id=request.session_id,
                enable_approval=True,
                enable_security=request.enable_security,
                user_permissions=request.user_permissions,
                user_id=request.user_id,
            )

            # 2. 记忆注入
            enhanced_text = await self._inject_memory(
                request.content, request.session_id, request.user_id
            )

            # 3. 构建输入状态
            input_state = {"messages": [HumanMessage(content=enhanced_text)]}
            config = get_thread_config(request.session_id)

            # 4. 执行并收集所有事件
            start_time = time.time()

            async for event in agent.astream(input_state, config=config):
                # 超时检查
                elapsed = time.time() - start_time
                if elapsed > AGENT_TIMEOUT:
                    return ChatResponse(
                        reply=f"处理超时（{elapsed:.0f}s），请稍后重试",
                        session_id=request.session_id,
                        workflow_status="timeout"
                    )

                # 处理事件
                event_result = self._process_event(event, request.session_id)
                if event_result:
                    event_type, event_data, state_update = event_result

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

            # 5. 提取最终回复
            reply = await self._extract_reply(final_state, workflow_completed)

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

    def _process_event(
        self,
        event: Dict[str, Any],
        session_id: str
    ) -> Optional[tuple]:
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
            approval_info = self._extract_approval_info(interrupt_data)

            if approval_info:
                # 保存审批状态
                try:
                    from app.services.session_state_manager import SessionStateManager
                    SessionStateManager.set_awaiting_approval(
                        session_id,
                        approval_data=approval_info
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

                # 发送状态更新
                status_msg = self._get_status_message(node_name)
                state_update = None

                # 尝试提取 state
                if isinstance(node_state, dict) and "messages" in node_state:
                    try:
                        state_update = {
                            "messages": [
                                {"type": type(m).__name__, "content": getattr(m, 'content', str(m))}
                                for m in node_state.get("messages", [])
                            ],
                            "final_report": node_state.get("final_report", ""),
                            "formatted_response": node_state.get("formatted_response", ""),
                            "intent_type": node_state.get("intent_type", "unknown"),
                            "diagnosis_round": node_state.get("diagnosis_round", 0),
                        }
                    except Exception:
                        state_update = {"raw_state": True}

                return (
                    EventType.STATUS,
                    {"status": "processing", "message": status_msg},
                    state_update
                )

        # 3. 处理自定义 complete 事件
        if event_type == "complete":
            state = event.get("state", {})
            return (
                EventType.STATUS,
                {"status": "completed", "message": "✅ 处理完成"},
                state
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

    def _extract_approval_info(self, interrupt_data: Any) -> Optional[Dict[str, Any]]:
        """从 interrupt 数据中提取审批信息"""
        try:
            if isinstance(interrupt_data, tuple) and len(interrupt_data) > 0:
                interrupt_obj = interrupt_data[0]
                if hasattr(interrupt_obj, 'value'):
                    approval_info = interrupt_obj.value

                    # 转换 DeepAgents HITLRequest 格式
                    action_requests = approval_info.get('action_requests', [])
                    commands = []
                    for req in action_requests:
                        tool_name = req.get('name', 'unknown')
                        tool_args = req.get('args', {})
                        description = req.get('description', '')

                        # 推断工具类型
                        if tool_name.startswith('delete_') or tool_name.startswith('restart_'):
                            tool_type = 'k8s'
                        elif 'prometheus' in tool_name.lower():
                            tool_type = 'prometheus'
                        else:
                            tool_type = 'k8s'

                        commands.append({
                            'type': tool_type,
                            'action': tool_name,
                            'params': tool_args,
                            'reason': description
                        })

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

    async def _inject_memory(
        self,
        text: str,
        session_id: str,
        user_id: int
    ) -> str:
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
                include_mem0=True,
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

    async def _extract_reply(
        self,
        final_state: Dict[str, Any],
        workflow_completed: bool
    ) -> Optional[str]:
        """提取最终回复"""
        try:
            if final_state:
                try:
                    final_state = ensure_final_report_in_state(final_state)
                except Exception as e:
                    logger.warning(f"⚠️ ensure_final_report_in_state 失败: {e}")

                # 按优先级提取回复
                reply = (
                    final_state.get("formatted_response", "") or
                    final_state.get("final_report", "") or
                    final_state.get("final_answer", "") or
                    final_state.get("response", "")
                )

                if reply:
                    logger.info(f"📝 从 final_state 提取到回复 (长度: {len(reply)})")
                    return reply

                # 从 messages 中提取
                messages = final_state.get("messages", [])
                if messages:
                    for msg in reversed(messages):
                        if isinstance(msg, dict):
                            if msg.get("type") == "AIMessage" and msg.get("content"):
                                return msg["content"]
                        elif isinstance(msg, AIMessage) and msg.content:
                            return msg.content

        except Exception as e:
            logger.error(f"❌ 提取回复失败: {e}")

        if workflow_completed:
            return "✅ 任务已完成，但没有生成文本回复。"

        return None

    def _get_status_message(self, node_name: str) -> str:
        """根据节点名获取状态消息"""
        status_map = {
            "intent_analysis": "🔍 正在分析意图...",
            "command_planning": "📋 正在规划命令...",
            "execute_diagnosis": "🔧 正在执行诊断...",
            "analyze_result": "📊 正在分析结果...",
        }
        return status_map.get(node_name, f"⚙️ 正在执行: {node_name}")


# 单例实例
_agent_chat_service: Optional[AgentChatService] = None


def get_agent_chat_service() -> AgentChatService:
    """获取 AgentChatService 单例"""
    global _agent_chat_service
    if _agent_chat_service is None:
        _agent_chat_service = AgentChatService()
    return _agent_chat_service
