"""DSPy LLM 适配器 - 将 LangChain LLM 包装为 DSPy LLM

基于 GitHub Issue #9245 的适配器模式
"""

from typing import Any, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage


class ModelResponse:
    """DSPy 兼容的响应模型"""

    def __init__(self, content: str, **kwargs):
        self.content = content
        self.kwargs = kwargs

    def __str__(self):
        return self.content

    def __repr__(self):
        content_preview = repr(self.content)[:50]
        return f"ModelResponse(content={content_preview}...)"


class DriverLM:
    """
    将 LangChain LLM 适配为 DSPy LLM

    这个类作为适配器层，将 LangChain 的 BaseChatModel 接口
    转换为 DSPy 可以使用的格式。
    """

    langchain_llm: BaseChatModel
    temperature: float
    max_tokens: int
    model: str
    model_type: str

    def __init__(
        self,
        langchain_llm: BaseChatModel,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ):
        """
        初始化适配器

        Args:
            langchain_llm: LangChain LLM 实例
            temperature: 温度参数
            max_tokens: 最大 token 数
        """
        self.langchain_llm = langchain_llm
        self.temperature = temperature
        self.max_tokens = max_tokens

        # 尝试获取模型名称
        self.model = getattr(self.langchain_llm, 'model_name', None) or \
                    getattr(self.langchain_llm, 'model', None) or \
                    "custom"
        self.model_type = "chat"

        # 基础属性（DSPy 兼容）
        self.cache = kwargs.get("cache", True)
        self.history = []

    def __call__(self, prompt: str, **kwargs) -> ModelResponse:
        """
        调用 LLM 生成响应

        Args:
            prompt: 输入提示词
            **kwargs: 额外参数（如 temperature, max_tokens）

        Returns:
            ModelResponse: DSPy 兼容的响应
        """
        try:
            # 合并参数
            temperature = kwargs.get("temperature", self.temperature)
            max_tokens = kwargs.get("max_tokens", self.max_tokens)

            # 构建消息
            messages = [HumanMessage(content=prompt)]

            # 调用 LangChain LLM
            response = self.langchain_llm.invoke(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # 提取内容
            content = response.content if hasattr(response, 'content') else str(response)

            # 记录历史
            self.history.append({"prompt": prompt, "response": content})

            return ModelResponse(content=content)

        except Exception as e:
            # 返回错误信息
            return ModelResponse(content=f"Error: {str(e)}")

    def get_model_info(self) -> dict:
        """获取模型信息"""
        return {
            "model": self.model,
            "provider": type(self.langchain_llm).__name__,
        }

    def clear_history(self):
        """清除历史记录"""
        self.history = []


def create_dspy_llm(
    langchain_llm: BaseChatModel,
    **kwargs
) -> DriverLM:
    """
    创建 DSPy LLM 实例

    Args:
        langchain_llm: LangChain LLM 实例
        **kwargs: 额外参数

    Returns:
        DriverLM: DSPy LLM 适配器
    """
    return DriverLM(langchain_llm=langchain_llm, **kwargs)


def create_dspy_llm_for_subagent(
    subagent_name: str,
    **kwargs
) -> DriverLM:
    """
    为指定 subagent 创建 DSPy LLM

    Args:
        subagent_name: 子智能体名称 (data-agent, analyze-agent, execute-agent)
        **kwargs: 额外参数

    Returns:
        DriverLM: DSPy LLM 适配器

    Raises:
        ValueError: 如果 subagent_name 无效
    """
    from app.core.llm_factory import LLMFactory

    # 验证 subagent 名称
    valid_subagents = ["data-agent", "analyze-agent", "execute-agent"]
    if subagent_name not in valid_subagents:
        raise ValueError(
            f"Invalid subagent_name: {subagent_name}. "
            f"Valid options: {', '.join(valid_subagents)}"
        )

    langchain_llm = LLMFactory.create_llm_for_subagent(subagent_name)
    return create_dspy_llm(langchain_llm=langchain_llm, **kwargs)
