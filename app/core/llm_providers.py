"""
LLM Provider 基类和具体实现

使用简单工厂模式，方便后期扩展新的 LLM Provider
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, cast

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
import logging

from app.core.config import Settings

logger = logging.getLogger(__name__)

# 尝试导入可选依赖
try:
    from langchain_anthropic import ChatAnthropic
except ImportError:
    ChatAnthropic = None  # type: ignore

try:
    from langchain_community.chat_models import ChatZhipuAI
except ImportError:
    ChatZhipuAI = None  # type: ignore

__all__ = [
    "BaseLLMProvider",
    "OpenAIProvider",
    "ClaudeProvider",
    "ZhipuProvider",
    "OllamaProvider",
    "OpenRouterProvider",
]


class BaseLLMProvider(ABC):
    """LLM Provider 基类"""

    def __init__(self, settings: Settings):
        self.settings = settings

    @abstractmethod
    def create_client(self, model_override: Optional[str] = None) -> BaseChatModel:
        """
        创建 LLM 客户端

        Args:
            model_override: 可选的模型名称，用于覆盖配置中的模型

        Returns:
            LLM 客户端实例
        """
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """
        验证配置是否有效

        Returns:
            True: 配置有效
            False: 配置无效
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider 名称"""
        pass

    def annotate_client(self, client: BaseChatModel, model_name: str) -> BaseChatModel:
        """为 LLM 客户端挂载诊断元数据"""
        setattr(client, "_ops_provider", self.provider_name)
        setattr(client, "_ops_model", model_name)
        return client


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Provider"""

    @property
    def provider_name(self) -> str:
        return "openai"

    def validate_config(self) -> bool:
        return self.settings.OPENAI_API_KEY is not None

    def create_client(self, model_override: Optional[str] = None) -> BaseChatModel:
        if not self.validate_config():
            raise ValueError(
                "OPENAI_API_KEY is not configured. "
                "Please set it in .env file or environment variables."
            )

        model_name = model_override or self.settings.OPENAI_MODEL
        logger.info(
            f"Creating OpenAI client: model={model_name}, "
            f"temperature={self.settings.OPENAI_TEMPERATURE}"
        )

        client = cast(Any, ChatOpenAI)(
            model=model_name,
            temperature=self.settings.OPENAI_TEMPERATURE,
            max_tokens=self.settings.OPENAI_MAX_TOKENS,
            api_key=cast(Any, self.settings.OPENAI_API_KEY),
            base_url=self.settings.OPENAI_BASE_URL,
            timeout=self.settings.OPENAI_REQUEST_TIMEOUT,
        )
        return self.annotate_client(client, model_name)


class ClaudeProvider(BaseLLMProvider):
    """Claude Provider"""

    @property
    def provider_name(self) -> str:
        return "claude"

    def validate_config(self) -> bool:
        return self.settings.CLAUDE_API_KEY is not None

    def create_client(self, model_override: Optional[str] = None) -> BaseChatModel:
        if ChatAnthropic is None:
            raise ImportError(
                "langchain-anthropic is not installed. "
                "Please install it with: pip install langchain-anthropic"
            )

        if not self.validate_config():
            raise ValueError(
                "CLAUDE_API_KEY is not configured. "
                "Please set it in .env file or environment variables."
            )

        model_name = model_override or self.settings.CLAUDE_MODEL
        logger.info(
            f"Creating Claude client: model={model_name}, "
            f"temperature={self.settings.CLAUDE_TEMPERATURE}"
        )

        client = cast(Any, ChatAnthropic)(
            model=model_name,
            model_name=model_name,
            temperature=self.settings.CLAUDE_TEMPERATURE,
            max_tokens=self.settings.CLAUDE_MAX_TOKENS,
            api_key=self.settings.CLAUDE_API_KEY,
            timeout=self.settings.CLAUDE_REQUEST_TIMEOUT,
        )
        return self.annotate_client(client, model_name)


class ZhipuProvider(BaseLLMProvider):
    """智谱 AI Provider"""

    @property
    def provider_name(self) -> str:
        return "zhipu"

    def validate_config(self) -> bool:
        return self.settings.ZHIPU_API_KEY is not None

    def create_client(self, model_override: Optional[str] = None) -> BaseChatModel:
        if ChatZhipuAI is None:
            raise ImportError(
                "langchain-community with ZhipuAI support is not installed. "
                "Please install it with: pip install langchain-community"
            )

        if not self.validate_config():
            raise ValueError(
                "ZHIPU_API_KEY is not configured. "
                "Please set it in .env file or environment variables."
            )

        model_name = model_override or self.settings.ZHIPU_MODEL
        logger.info(
            f"Creating ZhipuAI client: model={model_name}, "
            f"temperature={self.settings.ZHIPU_TEMPERATURE}"
        )

        client = cast(Any, ChatZhipuAI)(
            model=model_name,
            temperature=self.settings.ZHIPU_TEMPERATURE,
            api_key=self.settings.ZHIPU_API_KEY,
            request_timeout=self.settings.ZHIPU_REQUEST_TIMEOUT,
        )
        return self.annotate_client(client, model_name)


class OllamaProvider(BaseLLMProvider):
    """Ollama Provider (本地部署)"""

    @property
    def provider_name(self) -> str:
        return "ollama"

    def validate_config(self) -> bool:
        return True  # Ollama 不需要 API key

    def create_client(self, model_override: Optional[str] = None) -> BaseChatModel:
        model_name = model_override or self.settings.OLLAMA_MODEL

        # Ollama 的 OpenAI 兼容端点
        base_url = self.settings.OLLAMA_BASE_URL.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"

        logger.info(
            f"Creating Ollama client (OpenAI compatible): model={model_name}, "
            f"base_url={base_url}"
        )

        client = cast(Any, ChatOpenAI)(
            model=model_name,
            temperature=self.settings.OLLAMA_TEMPERATURE,
            base_url=base_url,
            api_key="ollama",
            timeout=600,
            streaming=True,
            max_retries=2,
            http_client=httpx.Client(
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                timeout=httpx.Timeout(120, connect=10),  # 连接超时10秒
            ),
        )
        return self.annotate_client(client, model_name)


class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter Provider"""

    @property
    def provider_name(self) -> str:
        return "openrouter"

    def validate_config(self) -> bool:
        return self.settings.OPENROUTER_API_KEY is not None

    def create_client(self, model_override: Optional[str] = None) -> BaseChatModel:
        if not self.validate_config():
            raise ValueError(
                "OPENROUTER_API_KEY is not configured. "
                "Please set it in .env file or environment variables."
            )

        model_name = model_override or self.settings.OPENROUTER_MODEL
        logger.info(
            f"Creating OpenRouter client: model={model_name}, "
            f"temperature={self.settings.OPENROUTER_TEMPERATURE}"
        )

        client = cast(Any, ChatOpenAI)(
            model=model_name,
            temperature=self.settings.OPENROUTER_TEMPERATURE,
            max_tokens=self.settings.OPENROUTER_MAX_TOKENS,
            api_key=cast(Any, self.settings.OPENROUTER_API_KEY),
            base_url=self.settings.OPENROUTER_BASE_URL,
            timeout=self.settings.OPENROUTER_REQUEST_TIMEOUT,
        )
        return self.annotate_client(client, model_name)


