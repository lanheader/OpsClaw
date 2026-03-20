"""调试日志工具模块 - 用于追踪 Agent、节点和工具的执行"""

import logging
import functools
import inspect
import time
import json
from typing import Any, Callable
from app.utils.logger import get_logger

logger = get_logger(__name__)


def log_agent_call(agent_name: str):
    """装饰器：记录 Agent 调用的详细信息"""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            frame = inspect.currentframe()
            caller_info = {
                "file": frame.f_back.f_code.co_filename.split("/")[-1],
                "function": frame.f_back.f_code.co_name,
                "line": frame.f_back.f_lineno,
            }
            start_time = time.time()

            logger.info("=" * 80)
            logger.info(f"🤖 [{agent_name}] 开始执行")
            logger.info(
                f"   📍 调用位置: {caller_info['file']}:{caller_info['line']} in {caller_info['function']}()"
            )
            logger.info(f"   📥 输入参数: {_format_args(args, kwargs)}")
            logger.info("=" * 80)

            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.info("=" * 80)
                logger.info(f"✅ [{agent_name}] 执行成功")
                logger.info(f"   ⏱️  耗时: {elapsed:.2f}s")
                logger.info(f"   📤 返回结果: {_format_result(result)}")
                logger.info("=" * 80)
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error("=" * 80)
                logger.error(f"❌ [{agent_name}] 执行失败")
                logger.error(f"   ⏱️  耗时: {elapsed:.2f}s")
                logger.error(f"   💥 错误: {type(e).__name__}: {str(e)}")
                logger.error(f"   📍 错误位置: {caller_info['file']}:{caller_info['line']}")
                logger.error("=" * 80)
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            frame = inspect.currentframe()
            caller_info = {
                "file": frame.f_back.f_code.co_filename.split("/")[-1],
                "function": frame.f_back.f_code.co_name,
                "line": frame.f_back.f_lineno,
            }
            start_time = time.time()

            logger.info("=" * 80)
            logger.info(f"🤖 [{agent_name}] 开始执行")
            logger.info(
                f"   📍 调用位置: {caller_info['file']}:{caller_info['line']} in {caller_info['function']}()"
            )
            logger.info(f"   📥 输入参数: {_format_args(args, kwargs)}")
            logger.info("=" * 80)

            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.info("=" * 80)
                logger.info(f"✅ [{agent_name}] 执行成功")
                logger.info(f"   ⏱️  耗时: {elapsed:.2f}s")
                logger.info(f"   📤 返回结果: {_format_result(result)}")
                logger.info("=" * 80)
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error("=" * 80)
                logger.error(f"❌ [{agent_name}] 执行失败")
                logger.error(f"   ⏱️  耗时: {elapsed:.2f}s")
                logger.error(f"   💥 错误: {type(e).__name__}: {str(e)}")
                logger.error(f"   📍 错误位置: {caller_info['file']}:{caller_info['line']}")
                logger.error("=" * 80)
                raise

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def log_node_execution(node_name: str):
    """装饰器：记录节点执行的详细信息"""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            frame = inspect.currentframe()
            caller_info = {
                "file": frame.f_back.f_code.co_filename.split("/")[-1],
                "function": frame.f_back.f_code.co_name,
                "line": frame.f_back.f_lineno,
            }
            start_time = time.time()

            state = args[0] if args else kwargs.get("state", {})
            session_id = state.get("session_id", "unknown")
            diagnosis_round = state.get("diagnosis_round", 0)

            logger.info("🔷" * 40)
            logger.info(f"📦 [节点] {node_name} - 开始执行")
            logger.info(f"   📍 位置: {caller_info['file']}:{caller_info['line']}")
            logger.info(f"   🆔 会话: {session_id}")
            logger.info(f"   🔄 诊断轮次: {diagnosis_round}")
            logger.info(f"   📊 状态快照: {_format_state_snapshot(state)}")
            logger.info("🔷" * 40)

            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.info("🔷" * 40)
                logger.info(f"✅ [节点] {node_name} - 执行完成")
                logger.info(f"   ⏱️  耗时: {elapsed:.2f}s")
                logger.info(f"   📊 状态变化: {_format_state_changes(state, result)}")
                logger.info("🔷" * 40)
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error("🔷" * 40)
                logger.error(f"❌ [节点] {node_name} - 执行失败")
                logger.error(f"   ⏱️  耗时: {elapsed:.2f}s")
                logger.error(f"   💥 错误: {type(e).__name__}: {str(e)}")
                logger.error("🔷" * 40)
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            frame = inspect.currentframe()
            caller_info = {
                "file": frame.f_back.f_code.co_filename.split("/")[-1],
                "function": frame.f_back.f_code.co_name,
                "line": frame.f_back.f_lineno,
            }
            start_time = time.time()

            state = args[0] if args else kwargs.get("state", {})
            session_id = state.get("session_id", "unknown")
            diagnosis_round = state.get("diagnosis_round", 0)

            logger.info("🔷" * 40)
            logger.info(f"📦 [节点] {node_name} - 开始执行")
            logger.info(f"   📍 位置: {caller_info['file']}:{caller_info['line']}")
            logger.info(f"   🆔 会话: {session_id}")
            logger.info(f"   🔄 诊断轮次: {diagnosis_round}")
            logger.info(f"   📊 状态快照: {_format_state_snapshot(state)}")
            logger.info("🔷" * 40)

            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.info("🔷" * 40)
                logger.info(f"✅ [节点] {node_name} - 执行完成")
                logger.info(f"   ⏱️  耗时: {elapsed:.2f}s")
                logger.info(f"   📊 状态变化: {_format_state_changes(state, result)}")
                logger.info("🔷" * 40)
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error("🔷" * 40)
                logger.error(f"❌ [节点] {node_name} - 执行失败")
                logger.error(f"   ⏱️  耗时: {elapsed:.2f}s")
                logger.error(f"   💥 错误: {type(e).__name__}: {str(e)}")
                logger.error("🔷" * 40)
                raise

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def log_llm_call(model_name: str = "LLM"):
    """装饰器：记录 LLM 调用的详细信息"""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            frame = inspect.currentframe()
            caller_info = {
                "file": frame.f_back.f_code.co_filename.split("/")[-1],
                "function": frame.f_back.f_code.co_name,
                "line": frame.f_back.f_lineno,
            }
            start_time = time.time()

            prompt = _extract_prompt(args, kwargs)

            logger.info("🧠" * 40)
            logger.info(f"🤖 [LLM] {model_name} - 开始调用")
            logger.info(
                f"   📍 位置: {caller_info['file']}:{caller_info['line']} in {caller_info['function']}()"
            )
            logger.info(f"   📝 Prompt 长度: {len(str(prompt))} 字符")
            logger.info(f"   📝 Prompt 预览: {str(prompt)[:200]}...")
            logger.info("🧠" * 40)

            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start_time
                response_text = _extract_response(result)

                logger.info("🧠" * 40)
                logger.info(f"✅ [LLM] {model_name} - 调用成功")
                logger.info(f"   ⏱️  耗时: {elapsed:.2f}s")
                logger.info(f"   📤 响应长度: {len(response_text)} 字符")
                logger.info(f"   📤 响应预览: {response_text[:200]}...")
                logger.info("🧠" * 40)
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error("🧠" * 40)
                logger.error(f"❌ [LLM] {model_name} - 调用失败")
                logger.error(f"   ⏱️  耗时: {elapsed:.2f}s")
                logger.error(f"   💥 错误: {type(e).__name__}: {str(e)}")
                logger.error("🧠" * 40)
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            frame = inspect.currentframe()
            caller_info = {
                "file": frame.f_back.f_code.co_filename.split("/")[-1],
                "function": frame.f_back.f_code.co_name,
                "line": frame.f_back.f_lineno,
            }
            start_time = time.time()

            prompt = _extract_prompt(args, kwargs)

            logger.info("🧠" * 40)
            logger.info(f"🤖 [LLM] {model_name} - 开始调用")
            logger.info(
                f"   📍 位置: {caller_info['file']}:{caller_info['line']} in {caller_info['function']}()"
            )
            logger.info(f"   📝 Prompt 长度: {len(str(prompt))} 字符")
            logger.info(f"   📝 Prompt 预览: {str(prompt)[:200]}...")
            logger.info("🧠" * 40)

            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                response_text = _extract_response(result)

                logger.info("🧠" * 40)
                logger.info(f"✅ [LLM] {model_name} - 调用成功")
                logger.info(f"   ⏱️  耗时: {elapsed:.2f}s")
                logger.info(f"   📤 响应长度: {len(response_text)} 字符")
                logger.info(f"   📤 响应预览: {response_text[:200]}...")
                logger.info("🧠" * 40)
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error("🧠" * 40)
                logger.error(f"❌ [LLM] {model_name} - 调用失败")
                logger.error(f"   ⏱️  耗时: {elapsed:.2f}s")
                logger.error(f"   💥 错误: {type(e).__name__}: {str(e)}")
                logger.error("🧠" * 40)
                raise

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# ========== 辅助函数 ==========


def _format_args(args: tuple, kwargs: dict) -> str:
    """格式化函数参数"""
    parts = []
    if args:
        args_str = ", ".join([_truncate(repr(arg), 100) for arg in args[1:]])
        if args_str:
            parts.append(args_str)
    if kwargs:
        kwargs_str = ", ".join([f"{k}={_truncate(repr(v), 100)}" for k, v in kwargs.items()])
        parts.append(kwargs_str)
    return ", ".join(parts) if parts else "(无参数)"


def _format_result(result: Any) -> str:
    """格式化返回结果"""
    if result is None:
        return "None"
    if isinstance(result, dict):
        keys = list(result.keys())[:5]
        preview = {k: result[k] for k in keys}
        return f"dict({len(result)} keys): {_truncate(str(preview), 200)}"
    return _truncate(repr(result), 200)


def _format_state_snapshot(state: dict) -> str:
    """格式化状态快照"""
    key_fields = [
        "intent_type",
        "intent_confidence",
        "diagnosis_round",
        "data_sufficient",
        "need_remediation",
        "approval_status",
    ]
    snapshot = {k: state.get(k) for k in key_fields if k in state}
    return json.dumps(snapshot, ensure_ascii=False)


def _format_state_changes(old_state: dict, new_state: dict) -> str:
    """格式化状态变化"""
    if not isinstance(new_state, dict):
        return "状态未变化"

    changes = []
    for key in new_state:
        if key in old_state and old_state[key] != new_state[key]:
            changes.append(f"{key}: {old_state[key]} → {new_state[key]}")

    return ", ".join(changes[:5]) if changes else "无变化"


def _extract_prompt(args: tuple, kwargs: dict) -> str:
    """提取 prompt 信息"""
    if args and len(args) > 1:
        if isinstance(args[1], str):
            return args[1]
        if isinstance(args[1], list):
            return str(args[1])
    if "prompt" in kwargs:
        return kwargs["prompt"]
    if "messages" in kwargs:
        return str(kwargs["messages"])
    return "(无法提取 prompt)"


def _extract_response(result: Any) -> str:
    """提取响应文本"""
    if isinstance(result, str):
        return result
    if hasattr(result, "content"):
        return str(result.content)
    if isinstance(result, dict) and "content" in result:
        return str(result["content"])
    return str(result)


def _truncate(text: str, max_length: int) -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."
