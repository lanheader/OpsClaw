"""批准意图识别服务"""

from typing import Dict, Any, Optional, List
from langchain_core.language_models import BaseChatModel
from app.utils.logger import get_logger
import json
import re

logger = get_logger(__name__)

# 批准关键词列表
APPROVAL_KEYWORDS: List[str] = [
    "批准",
    "同意",
    "确认",
    "可以",
    "好的",
    "没问题",
    "执行",
    "approve",
    "yes",
    "ok",
    "go",
    "proceed",
    "continue",
]

# 拒绝关键词列表
REJECTION_KEYWORDS: List[str] = [
    "拒绝",
    "取消",
    "不要",
    "不行",
    "算了",
    "停止",
    "reject",
    "no",
    "cancel",
    "stop",
    "abort",
    "deny",
]


async def classify_approval_intent(
    user_input: str, llm: BaseChatModel, approval_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    识别用户在批准上下文中的意图

    Args:
        user_input: 用户输入
        llm: LLM 实例
        approval_context: 批准上下文（待执行的命令等）

    Returns:
        {
            "intent_type": "approval" | "rejection" | "clarification" | "other",
            "confidence": 0.0-1.0,
            "reasoning": "判断理由"
        }
    """
    logger.info(f"开始识别批准意图，用户输入: {user_input}")

    # 构建提示词
    commands_summary = approval_context.get("commands_summary", "未知操作")
    risk_level = approval_context.get("risk_level", "未知")

    system_prompt = """你是一个专业的意图识别助手，专门识别用户对操作批准请求的响应意图。

<role_definition>
你的核心职责是：
- 准确识别用户是否同意执行操作（批准）
- 准确识别用户是否拒绝执行操作（拒绝）
- 识别用户是否在询问更多信息（澄清）
- 识别用户是否提出了新的请求（其他）
</role_definition>

<intent_types>
1. approval（批准）
   - 用户明确表示同意、批准、确认执行
   - 示例：好的、可以、同意、执行吧、没问题、OK、yes、approve、go ahead、继续、开始吧

2. rejection（拒绝）
   - 用户明确表示拒绝、取消、不同意
   - 示例：不要、取消、拒绝、不行、算了、no、cancel、reject、stop、别执行

3. clarification（澄清）
   - 用户在询问更多信息、请求解释
   - 示例：这个命令是做什么的？、有风险吗？、能详细说明一下吗？、为什么要执行这个？

4. other（其他）
   - 用户提出了新的请求，与批准无关
   - 示例：查询 Pod 状态、帮我看看日志、重启服务
</intent_types>

<guidelines>
- 优先识别批准和拒绝意图（这是最重要的）
- 对于模糊的表达，如果有任何批准或拒绝的倾向，就识别为对应类型
- 只有当用户明确提出新问题或新请求时，才识别为 other
- 置信度评估：
  * 0.9-1.0: 非常明确的表达（如"批准"、"拒绝"）
  * 0.7-0.9: 清晰的表达（如"可以"、"不要"）
  * 0.5-0.7: 有一定倾向但不够明确（如"好吧"、"算了"）
  * 0.0-0.5: 模糊不清或无关
</guidelines>
"""

    user_prompt = f"""当前上下文：
系统刚刚请求用户批准执行以下操作：

操作内容：
{commands_summary}

风险等级：{risk_level}

用户回复：
{user_input}

请分析用户的意图，并以 JSON 格式返回：
{{
    "intent_type": "approval | rejection | clarification | other",
    "confidence": 0.0-1.0,
    "reasoning": "判断理由（简短说明为什么这样判断）"
}}

只返回 JSON，不要有其他内容。
"""

    try:
        # 调用 LLM
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = await llm.ainvoke(messages)
        response_text = response.content.strip()

        logger.info(f"LLM 响应: {response_text}")

        # 解析 JSON
        result = _parse_json_response(response_text)

        logger.info(f"意图识别结果: {result}")
        return result

    except Exception as e:
        logger.error(f"意图识别失败: {e}", exc_info=True)
        # 返回默认结果
        return {"intent_type": "other", "confidence": 0.0, "reasoning": f"识别失败: {str(e)}"}


def _parse_json_response(response_text: str) -> Dict[str, Any]:
    """解析 JSON 响应"""
    try:
        # 尝试直接解析
        return json.loads(response_text)
    except json.JSONDecodeError:
        # 尝试提取 JSON
        json_match = re.search(r"\{[^{}]*\}", response_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # 解析失败，返回默认值
        logger.warning(f"无法解析 JSON 响应: {response_text}")
        return {"intent_type": "other", "confidence": 0.0, "reasoning": "无法解析响应"}


def is_approval_keyword(text: str) -> bool:
    """
    快速检查是否包含批准关键词（用于快速路径）

    Args:
        text: 用户输入

    Returns:
        是否包含批准关键词
    """
    text = text.lower().strip()
    return any(keyword in text for keyword in APPROVAL_KEYWORDS)


def is_rejection_keyword(text: str) -> bool:
    """
    快速检查是否包含拒绝关键词（用于快速路径）

    Args:
        text: 用户输入

    Returns:
        是否包含拒绝关键词
    """
    text = text.lower().strip()
    return any(keyword in text for keyword in REJECTION_KEYWORDS)
