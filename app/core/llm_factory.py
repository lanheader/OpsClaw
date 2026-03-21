# app/core/llm_factory.py
"""LLM 工厂类 - 支持多个 LLM 提供商"""

from langchain_core.language_models import BaseChatModel
from typing import Any, Dict, Optional, cast
import logging

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LLMFactory:
    """
    LLM 工厂类。

    根据配置创建不同的 LLM 客户端（OpenAI, Claude, ZhipuAI, Ollama, OpenRouter）。
    """

    _client_cache: Dict[str, Any] = {}

    @staticmethod
    def create_llm(
        provider: Optional[str] = None,
        settings: Optional[Settings] = None,
    ) -> Any:
        """
        创建 LLM 客户端。

        参数：
            provider: LLM 提供商（openai, claude, zhipu, ollama, openrouter）
            settings: 配置对象，如果为 None 则使用全局配置
        """
        if settings is None:
            settings = get_settings()

        if provider is None:
            provider = settings.DEFAULT_LLM_PROVIDER

        logger.info(f"Creating LLM client for provider: {provider}")
        return LLMFactory._create_provider_client(provider=provider, settings=settings)

    @staticmethod
    def create_llm_for_subagent(
        subagent_name: str,
        settings: Optional[Settings] = None,
    ) -> Any:
        """
        为指定 subagent 创建专用 LLM 客户端（单模型，无降级）。

        参数：
            subagent_name: 子智能体名称（如 "intent-agent"）
            settings: 配置对象，如果为 None 则使用全局配置

        返回：
            LLM 客户端实例
        """
        if settings is None:
            settings = get_settings()

        # 获取 subagent 的模型配置（直接使用模型名）
        model = settings.get_subagent_model(subagent_name).strip()
        provider = settings.DEFAULT_LLM_PROVIDER

        # 使用缓存避免重复创建
        cache_key = f"{provider}:{model}"
        if cache_key not in LLMFactory._client_cache:
            try:
                logger.info(f"Creating LLM for {subagent_name}: {cache_key}")
                LLMFactory._client_cache[cache_key] = LLMFactory._create_provider_client(
                    provider=provider,
                    settings=settings,
                    model_override=model,
                )
            except Exception as exc:
                # 降级到默认 provider 的默认模型
                logger.warning(
                    f"无法创建 {subagent_name} 的专用 LLM ({cache_key}): {exc}，降级到默认配置"
                )
                return LLMFactory._create_provider_client(
                    provider=settings.DEFAULT_LLM_PROVIDER,
                    settings=settings,
                )

        return LLMFactory._client_cache[cache_key]

    @staticmethod
    def _create_provider_client(
        provider: str,
        settings: Settings,
        model_override: Optional[str] = None,
    ) -> BaseChatModel:
        if provider == "openai":
            return LLMFactory._create_openai_llm(settings, model_override=model_override)
        elif provider == "claude":
            return LLMFactory._create_claude_llm(settings, model_override=model_override)
        elif provider == "zhipu":
            return LLMFactory._create_zhipu_llm(settings, model_override=model_override)
        elif provider == "ollama":
            return LLMFactory._create_ollama_llm(settings, model_override=model_override)
        elif provider == "openrouter":
            return LLMFactory._create_openrouter_llm(settings, model_override=model_override)
        else:
            raise ValueError(
                f"Unsupported LLM provider: {provider}. "
                f"Supported providers: openai, claude, zhipu, ollama, openrouter"
            )

    @staticmethod
    def _create_openai_llm(
        settings: Settings, model_override: Optional[str] = None
    ) -> BaseChatModel:
        """
        创建 OpenAI LLM 客户端。

        参数：
            settings: 配置对象
            model_override: 可选的模型名称，用于覆盖配置中的模型

        返回：
            ChatOpenAI 实例

        异常：
            ValueError: 如果 API key 未配置
        """
        from langchain_openai import ChatOpenAI

        if not settings.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY is not configured. "
                "Please set it in .env file or environment variables."
            )

        model_name = model_override or settings.OPENAI_MODEL
        logger.info(
            f"Creating OpenAI client: model={model_name}, "
            f"temperature={settings.OPENAI_TEMPERATURE}, "
            f"timeout={settings.OPENAI_REQUEST_TIMEOUT}s"
        )

        openai_kwargs = {
            "model": model_name,
            "temperature": settings.OPENAI_TEMPERATURE,
            "max_tokens": settings.OPENAI_MAX_TOKENS,
            "api_key": cast(Any, settings.OPENAI_API_KEY),
            "base_url": settings.OPENAI_BASE_URL,
            "timeout": settings.OPENAI_REQUEST_TIMEOUT,
        }
        return cast(Any, ChatOpenAI)(**openai_kwargs)

    @staticmethod
    def _create_claude_llm(
        settings: Settings, model_override: Optional[str] = None
    ) -> BaseChatModel:
        """
        创建 Claude LLM 客户端。

        参数：
            settings: 配置对象
            model_override: 可选的模型名称，用于覆盖配置中的模型

        返回：
            ChatAnthropic 实例

        异常：
            ValueError: 如果 API key 未配置
            ImportError: 如果 langchain-anthropic 未安装
        """
        if not settings.CLAUDE_API_KEY:
            raise ValueError(
                "CLAUDE_API_KEY is not configured. "
                "Please set it in .env file or environment variables."
            )

        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            raise ImportError(
                "langchain-anthropic is not installed. "
                "Please install it with: pip install langchain-anthropic"
            )

        model_name = model_override or settings.CLAUDE_MODEL
        logger.info(
            f"Creating Claude client: model={model_name}, "
            f"temperature={settings.CLAUDE_TEMPERATURE}, "
            f"timeout={settings.CLAUDE_REQUEST_TIMEOUT}s"
        )

        claude_kwargs = {
            "model": model_name,
            "model_name": model_name,
            "temperature": settings.CLAUDE_TEMPERATURE,
            "max_tokens": settings.CLAUDE_MAX_TOKENS,
            "api_key": settings.CLAUDE_API_KEY,
            "timeout": settings.CLAUDE_REQUEST_TIMEOUT,
        }
        return cast(Any, ChatAnthropic)(**claude_kwargs)

    @staticmethod
    def _create_zhipu_llm(
        settings: Settings, model_override: Optional[str] = None
    ) -> BaseChatModel:
        """
        创建智谱 AI LLM 客户端。

        参数：
            settings: 配置对象
            model_override: 可选的模型名称，用于覆盖配置中的模型

        返回：
            ChatZhipuAI 实例

        异常：
            ValueError: 如果 API key 未配置
            ImportError: 如果 langchain-community 未安装
        """
        if not settings.ZHIPU_API_KEY:
            raise ValueError(
                "ZHIPU_API_KEY is not configured. "
                "Please set it in .env file or environment variables."
            )

        try:
            from langchain_community.chat_models import ChatZhipuAI
        except ImportError:
            raise ImportError(
                "langchain-community with ZhipuAI support is not installed. "
                "Please install it with: pip install langchain-community"
            )

        model_name = model_override or settings.ZHIPU_MODEL
        logger.info(
            f"Creating ZhipuAI client: model={model_name}, "
            f"temperature={settings.ZHIPU_TEMPERATURE}, "
            f"timeout={settings.ZHIPU_REQUEST_TIMEOUT}s"
        )

        zhipu_kwargs = {
            "model": model_name,
            "temperature": settings.ZHIPU_TEMPERATURE,
            "api_key": settings.ZHIPU_API_KEY,
            "request_timeout": settings.ZHIPU_REQUEST_TIMEOUT,
        }
        return cast(Any, ChatZhipuAI)(**zhipu_kwargs)

    @staticmethod
    def _create_ollama_llm(
        settings: Settings, model_override: Optional[str] = None
    ) -> BaseChatModel:
        """
        创建 Ollama LLM 客户端（本地部署）。

        参数：
            settings: 配置对象
            model_override: 可选的模型名称，用于覆盖配置中的模型

        返回：
            ChatOllama 实例

        异常：
            ImportError: 如果 langchain-ollama 未安装
        """
        try:
            from langchain_ollama import ChatOllama
        except ImportError:
            # 降级尝试使用 langchain-community
            try:
                from langchain_community.chat_models import ChatOllama
            except ImportError:
                raise ImportError(
                    "Ollama support not found. "
                    "Please install it with: pip install langchain-ollama"
                )

        model_name = model_override or settings.OLLAMA_MODEL
        logger.info(
            f"Creating Ollama client: model={model_name}, " f"base_url={settings.OLLAMA_BASE_URL}"
        )

        ollama_kwargs = {
            "model": model_name,
            "temperature": settings.OLLAMA_TEMPERATURE,
            "base_url": settings.OLLAMA_BASE_URL,
        }
        return cast(Any, ChatOllama)(**ollama_kwargs)

    @staticmethod
    def _create_openrouter_llm(
        settings: Settings, model_override: Optional[str] = None
    ) -> BaseChatModel:
        """
        创建 OpenRouter LLM 客户端。

        OpenRouter 是一个聚合服务，提供对多个 LLM 提供商的统一访问接口。
        使用 OpenAI 兼容的 API 格式。

        参数：
            settings: 配置对象
            model_override: 可选的模型名称，用于覆盖配置中的模型

        返回：
            ChatOpenAI 实例（配置为使用 OpenRouter）

        异常：
            ValueError: 如果 API key 未配置

        支持的模型示例：
            - anthropic/claude-3.5-sonnet
            - anthropic/claude-3-opus
            - openai/gpt-4-turbo
            - openai/o1-preview
            - google/gemini-pro-1.5
            - meta-llama/llama-3.1-405b-instruct
            - mistralai/mistral-large
        """
        from langchain_openai import ChatOpenAI

        if not settings.OPENROUTER_API_KEY:
            raise ValueError(
                "OPENROUTER_API_KEY is not configured. "
                "Please set it in .env file or environment variables."
            )

        model_name = model_override or settings.OPENROUTER_MODEL
        logger.info(
            f"Creating OpenRouter client: model={model_name}, "
            f"temperature={settings.OPENROUTER_TEMPERATURE}, "
            f"timeout={settings.OPENROUTER_REQUEST_TIMEOUT}s"
        )

        openrouter_kwargs = {
            "model": model_name,
            "temperature": settings.OPENROUTER_TEMPERATURE,
            "max_tokens": settings.OPENROUTER_MAX_TOKENS,
            "api_key": cast(Any, settings.OPENROUTER_API_KEY),
            "base_url": settings.OPENROUTER_BASE_URL,
            "timeout": settings.OPENROUTER_REQUEST_TIMEOUT,
        }
        return cast(Any, ChatOpenAI)(**openrouter_kwargs)


# LLM 客户端单例
_llm_instance: Optional[Any] = None


def get_llm(
    provider: Optional[str] = None,
    force_new: bool = False,
) -> Any:
    """
    获取 LLM 客户端单例。

    参数：
        provider: LLM 提供商（可选）
        force_new: 强制创建新实例（默认使用单例）
    """
    global _llm_instance

    if _llm_instance is None or force_new:
        settings = get_settings()

        if not settings.validate_llm_config():
            raise ValueError(
                f"LLM configuration is invalid for provider: {settings.DEFAULT_LLM_PROVIDER}. "
                f"Please check your .env file."
            )

        _llm_instance = LLMFactory.create_llm(provider=provider, settings=settings)
        logger.info("LLM client initialized successfully")

    return _llm_instance


def reset_llm():
    """
    重置 LLM 单例（用于测试）。
    """
    global _llm_instance
    _llm_instance = None
    LLMFactory._client_cache.clear()
