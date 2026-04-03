"""
LLM 辅助工具函数

提供通用的 LLM 响应解析和处理函数
"""

import json
import re
from typing import Any, Dict, Iterable, Optional, TypeVar, Type

from langchain_core.messages import AIMessage, HumanMessage

from app.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=Dict[str, Any])


def _normalize_message_content(content: Any) -> str:
    """将 LangChain message content 规范化为纯文本。"""
    if content is None:
        return ""

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    parts.append(text)
                continue

            if not isinstance(item, dict):
                continue

            item_type = item.get("type")
            if item_type == "text":
                text = str(item.get("text", "")).strip()
                if text:
                    parts.append(text)

        return "\n".join(parts).strip()

    if isinstance(content, dict):
        text = content.get("text")  # type: ignore[assignment]
        return str(text).strip() if text else ""

    return str(content).strip()


def _extract_best_ai_reply(search_messages: list[Any]) -> str:
    """从消息列表（逆序搜索）中找到最后一个有内容的非工具调用 AI 消息。"""
    for message in reversed(search_messages):
        if isinstance(message, AIMessage):
            if getattr(message, "tool_calls", None):
                continue
            text = _normalize_message_content(getattr(message, "content", None))
            if text:
                return text

        elif isinstance(message, dict) and message.get("type") in {"ai", "assistant"}:
            if message.get("tool_calls"):
                continue
            text = _normalize_message_content(message.get("content"))
            if text:
                return text

    return ""


def extract_final_report_from_messages(messages: Iterable[Any]) -> str:
    """从消息列表中提取最后一个有意义的 AI 回复。

    先搜索当前轮次（最后一条 HumanMessage 之后），若无有效结果
    则回退到搜索全部消息，避免因框架二次 LLM 调用返回空内容
    而丢失上一轮已生成的有效回复。
    """
    all_messages: list[Any] = list(messages)

    # 1. 优先从当前轮次（最后一条 HumanMessage 之后）搜索
    current_turn: list[Any] = []
    for message in reversed(all_messages):
        is_human = isinstance(message, HumanMessage) or (
            isinstance(message, dict) and message.get("type") == "human"
        )
        if is_human:
            break
        current_turn.append(message)

    result = _extract_best_ai_reply(current_turn)
    if result:
        return result

    # 2. 当前轮次无有效回复时，搜索全部消息（处理框架二次空调用场景）
    logger.debug("当前轮次无有效 AI 回复，回退到全量消息搜索")
    return _extract_best_ai_reply(all_messages)


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _stringify_items(items: list[Any], prefix: str = "- ") -> list[str]:
    lines: list[str] = []
    for item in items:
        if isinstance(item, dict):
            description = (
                item.get("description")
                or item.get("action")
                or item.get("title")
                or item.get("summary")
                or item.get("content")
            )
            if description:
                lines.append(f"{prefix}{description}")
                continue

        text = _normalize_message_content(item)
        if text:
            lines.append(f"{prefix}{text}")

    return lines


def _format_key_label(key: str) -> str:
    mapping = {
        "total_pods": "总 Pod 数",
        "running": "Running",
        "pending": "Pending",
        "failed": "Failed",
        "total": "总数",
        "success": "成功数",
    }
    return mapping.get(key, key.replace("_", " "))


def _build_query_report(
    analysis_result: Dict[str, Any],
    collected_data: Dict[str, Any],
    recommendation_lines: list[str],
) -> str:
    summary = analysis_result.get("summary") if isinstance(analysis_result.get("summary"), dict) else {}
    anomalies = analysis_result.get("anomalies") if isinstance(analysis_result.get("anomalies"), list) else []

    lines = ["✅ 任务完成", ""]
    if summary:
        for key, value in summary.items():
            lines.append(f"{_format_key_label(str(key))}: {value}")
        lines.append("")

    if anomalies:
        lines.append("异常项:")
        for item in anomalies:
            if isinstance(item, dict):
                resource = item.get("resource") or item.get("name") or "未知资源"
                status = item.get("status") or "未知状态"
                reason = item.get("reason") or item.get("description") or ""
                suffix = f", {reason}" if reason else ""
                lines.append(f"- {resource} ({status}{suffix})")
        lines.append("")

    if not summary and collected_data:
        lines.append("结果摘要:")
        lines.append(f"- 已采集数据项: {', '.join(sorted(collected_data.keys()))}")
        lines.append("")

    if recommendation_lines:
        lines.append("建议:")
        lines.extend(recommendation_lines)

    return "\n".join(line for line in lines if line is not None).strip()


def _build_operate_report(
    state: Dict[str, Any],
    collected_data: Dict[str, Any],
    recommendation_lines: list[str],
    plan_lines: list[str],
) -> str:
    remediation_plan = state.get("remediation_plan") if isinstance(state.get("remediation_plan"), dict) else {}
    verification = collected_data.get("verification") if isinstance(collected_data.get("verification"), dict) else {}
    action = _normalize_message_content(remediation_plan.get("action"))  # type: ignore[union-attr]
    success = bool(state.get("execution_success"))

    lines = ["🚀 执行成功" if success else "❌ 执行失败", ""]
    if action:
        lines.append(f"操作: {action}")
    if verification:
        lines.extend(["", "验证:"])
        for key, value in verification.items():
            lines.append(f"- {_format_key_label(str(key))}: {value}")
    if plan_lines:
        lines.extend(["", "执行结果:"])
        lines.extend(plan_lines)
    if recommendation_lines:
        lines.extend(["", "后续建议:"])
        lines.extend(recommendation_lines)

    return "\n".join(lines).strip()


def synthesize_final_report_from_state(state: Dict[str, Any]) -> str:
    """从结构化 state 字段中兜底组装用户可读的最终回复。"""
    intent_type = state.get("intent_type", "unknown")
    root_cause = _normalize_message_content(state.get("root_cause"))
    severity = _normalize_message_content(state.get("severity"))

    analysis_result = state.get("analysis_result") if isinstance(state.get("analysis_result"), dict) else {}
    remediation_plan = state.get("remediation_plan") if isinstance(state.get("remediation_plan"), dict) else {}
    collected_data = state.get("collected_data") if isinstance(state.get("collected_data"), dict) else {}

    evidence_lines = _stringify_items(_ensure_list(analysis_result.get("evidence")))  # type: ignore[union-attr]
    recommendation_lines = _stringify_items(_ensure_list(analysis_result.get("recommendations")))  # type: ignore[union-attr]
    plan_lines = _stringify_items(_ensure_list(remediation_plan.get("steps")))  # type: ignore[union-attr]

    recommendation_lines.extend(
        line
        for line in _stringify_items(_ensure_list(remediation_plan.get("recommendations")))  # type: ignore[union-attr]
        if line not in recommendation_lines
    )
    plan_lines = [line for line in plan_lines if line not in recommendation_lines]

    summary_lines: list[str] = []
    if collected_data:
        summary_lines.append(f"- 已采集数据项: {', '.join(sorted(collected_data.keys()))}")

    if intent_type == "query":
        return _build_query_report(analysis_result, collected_data, recommendation_lines)  # type: ignore[arg-type]

    if intent_type == "operate":
        return _build_operate_report(state, collected_data, recommendation_lines, plan_lines)  # type: ignore[arg-type]

    if intent_type == "diagnose" or root_cause or evidence_lines:
        lines = ["🔍 诊断结果", ""]
        if root_cause:
            lines.append(f"根本原因: {root_cause}")
        if severity:
            lines.append(f"严重程度: {severity}")
        if summary_lines:
            lines.extend(["", "补充信息:"])
            lines.extend(summary_lines)
        if evidence_lines:
            lines.extend(["", "关键证据:"])
            lines.extend(evidence_lines)
        if recommendation_lines or plan_lines:
            lines.extend(["", "建议方案:"])
            lines.extend(recommendation_lines)
            lines.extend(plan_lines)
        return "\n".join(lines).strip()

    if recommendation_lines or plan_lines:
        lines = ["✅ 任务完成", ""]
        if summary_lines:
            lines.extend(["结果摘要:"])
            lines.extend(summary_lines)
            lines.append("")
        lines.append("后续建议:")
        lines.extend(recommendation_lines or plan_lines)
        return "\n".join(lines).strip()

    return ""


def _safe_merge_state(state: Dict[str, Any], new_key: str, new_value: Any) -> Dict[str, Any]:
    """
    安全地合并状态，处理 LangGraph 内部对象（如 Overwrite）不可序列化的问题。

    LangGraph 的 state 可能包含 Overwrite 等内部对象，直接使用 {**state, ...} 会失败。
    这个函数先尝试直接合并，失败时则构建一个新的可序列化字典。
    """
    try:
        return {**state, new_key: new_value}
    except (TypeError, ValueError) as e:
        logger.debug(f"直接合并状态失败（可能包含不可序列化对象）: {e}")
        # 构建一个新的可序列化字典
        safe_state: Dict[str, Any] = {}
        for key, value in state.items():
            try:
                # 尝试复制值
                if isinstance(value, (str, int, float, bool, type(None))):
                    safe_state[key] = value
                elif isinstance(value, (list, dict)):
                    safe_state[key] = value
                elif hasattr(value, '__dict__'):
                    # 对于复杂对象，只保存字符串表示
                    safe_state[key] = str(value)
                else:
                    safe_state[key] = value
            except Exception:
                safe_state[key] = f"<non-serializable: {type(value).__name__}>"

        safe_state[new_key] = new_value
        return safe_state


def ensure_final_report_in_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """在状态中补齐 final_report，已存在时保持原值。"""
    # 如果 state 为空或不是字典，直接返回
    if not state or not isinstance(state, dict):
        return state

    # 如果已有 final_report，直接返回
    existing_report = _normalize_message_content(state.get("final_report"))
    if existing_report:
        return state

    # 尝试从直接 state 合成报告
    synthesized_report = synthesize_final_report_from_state(state)
    if synthesized_report:
        return _safe_merge_state(state, "final_report", synthesized_report)

    # 尝试从 messages 提取
    messages = state.get("messages", [])
    final_report = extract_final_report_from_messages(messages)
    if final_report:
        return _safe_merge_state(state, "final_report", final_report)

    # 兜底：从 _raw_node_state 提取（LangGraph 节点事件可能没有 messages 字段）
    raw_node_state = state.get("_raw_node_state")
    if isinstance(raw_node_state, dict):
        # 先尝试合成
        synthesized_report = synthesize_final_report_from_state(raw_node_state)
        if synthesized_report:
            return _safe_merge_state(state, "final_report", synthesized_report)

        # 再尝试从 messages 提取
        raw_messages = raw_node_state.get("messages", [])
        final_report = extract_final_report_from_messages(raw_messages)
        if final_report:
            return _safe_merge_state(state, "final_report", final_report)

    return state


def extract_json_from_llm_response(
    content: str,
    default: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    从 LLM 响应中提取 JSON 数据

    支持多种格式：
    1. ```json ... ``` 代码块
    2. ``` ... ``` 代码块
    3. 纯 JSON 对象

    Args:
        content: LLM 返回的内容
        default: 解析失败时返回的默认值

    Returns:
        解析后的 JSON 字典，失败返回默认值
    """
    if default is None:
        default = {}

    content = content.strip()

    # 尝试提取 ```json 代码块
    if "```json" in content:
        try:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            if json_end > json_start:
                json_str = content[json_start:json_end].strip()
                return json.loads(json_str)  # type: ignore[no-any-return]
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug(f"解析 ```json 代码块失败: {e}")

    # 尝试提取 ``` 代码块
    if "```" in content:
        try:
            json_start = content.find("```") + 3
            # 跳过语言标识符（如 "json"）
            while json_start < len(content) and content[json_start] not in ["\n", "{", "["]:
                json_start += 1

            json_end = content.find("```", json_start)
            if json_end > json_start:
                json_str = content[json_start:json_end].strip()
                return json.loads(json_str)  # type: ignore[no-any-return]
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug(f"解析 ``` 代码块失败: {e}")

    # 尝试直接解析
    try:
        return json.loads(content)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        pass

    # 尝试提取花括号内的 JSON
    try:
        start = content.find("{")
        if start >= 0:
            end = content.rfind("}") + 1
            if end > start:
                json_str = content[start:end]
                return json.loads(json_str)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, ValueError) as e:
        logger.debug(f"提取 JSON 对象失败: {e}")

    # 尝试提取方括号内的 JSON 数组
    try:
        start = content.find("[")
        if start >= 0:
            end = content.rfind("]") + 1
            if end > start:
                json_str = content[start:end]
                return json.loads(json_str)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, ValueError) as e:
        logger.debug(f"提取 JSON 数组失败: {e}")

    logger.warning(f"无法解析 JSON，内容预览: {content[:200]}")
    return default


def parse_structured_response(
    content: str,
    response_model: Type[T],
    default: Optional[T] = None
) -> T:
    """
    解析结构化响应（使用 Pydantic 模型）

    Args:
        content: LLM 返回的内容
        response_model: Pydantic 模型类
        default: 解析失败时返回的默认值

    Returns:
        解析后的模型实例
    """
    json_data = extract_json_from_llm_response(content)
    if not json_data:
        return default or response_model()

    try:
        return response_model(**json_data)
    except (TypeError, ValueError) as e:
        logger.warning(f"无法将 JSON 转换为 {response_model.__name__}: {e}")
        return default or response_model()


__all__ = [
    "extract_json_from_llm_response",
    "parse_structured_response",
    "extract_final_report_from_messages",
    "ensure_final_report_in_state",
    "synthesize_final_report_from_state",
]
