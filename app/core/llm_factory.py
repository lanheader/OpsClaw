"""
记忆增强的 LLM 工厂类

使用简单工厂模式，支持：
- 创建 LLM 客户端（多个提供商）
- 创建 Embedding 客户端（向量检索）
- 易于扩展新的 Provider
"""

from langchain_core.language_models import BaseChatModel
from typing import Any, Dict, Optional, Type
import logging
import socket

from app.core.config import Settings, get_settings
from app.core.llm_providers import (
    BaseLLMProvider,
    OpenAIProvider,
    ClaudeProvider,
    ZhipuProvider,
    OllamaProvider,
    OpenRouterProvider,
)

logger = logging.getLogger(__name__)


class LLMFactory:
    """
    LLM 工厂类（简单工厂模式）

    根据配置创建不同的 LLM 客户端。
    新增 Provider 只需：
    1. 在 llm_providers.py 中创建新的 Provider 类
    2. 在 PROVIDER_REGISTRY 中注册
    """

    _client_cache: Dict[str, Any] = {}
    _connection_tested: Dict[str, bool] = {}

    # Provider 注册表：provider_name -> Provider 类
    PROVIDER_REGISTRY: Dict[str, Type[BaseLLMProvider]] = {
        "openai": OpenAIProvider,
        "claude": ClaudeProvider,
        "zhipu": ZhipuProvider,
        "ollama": OllamaProvider,
        "openrouter": OpenRouterProvider,
    }

    @staticmethod
    def quick_test_connection(provider: str, settings: Optional[Settings] = None) -> bool:
        """
        快速测试 LLM 连接（只测试地址和端口，不发送消息）

        Args:
            provider: LLM 提供商
            settings: 配置对象

        Returns:
            True: 连接正常
            False: 连接失败
        """
        if settings is None:
            settings = get_settings()

        # 检查缓存
        cache_key = f"{provider}_connection"
        if cache_key in LLMFactory._connection_tested:
            return LLMFactory._connection_tested[cache_key]

        try:
            if provider == "ollama":
                # 测试 Ollama 地址和端口
                base_url = settings.OLLAMA_BASE_URL
                # 解析 host 和 port
                if "://" in base_url:
                    host_port = base_url.split("://")[1].split("/")[0]
                else:
                    host_port = base_url.split("/")[0]

                if ":" in host_port:
                    host, port = host_port.split(":")
                    port = int(port)  # type: ignore[assignment]
                else:
                    host = host_port
                    port = 11434  # Ollama 默认端口  # type: ignore[assignment]

                # 快速 socket 连接测试（超时 2 秒）
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((host, port))
                sock.close()

                if result == 0:
                    logger.info(f"✅ Ollama 连接测试通过: {host}:{port}")
                    LLMFactory._connection_tested[cache_key] = True
                    return True
                else:
                    logger.warning(f"⚠️ Ollama 连接测试失败: {host}:{port} (错误码: {result})")
                    LLMFactory._connection_tested[cache_key] = False
                    return False

            elif provider == "openai":
                # OpenAI 使用 HTTPS，测试 api.openai.com:443
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex(("api.openai.com", 443))
                sock.close()

                if result == 0:
                    logger.info("✅ OpenAI 连接测试通过")
                    LLMFactory._connection_tested[cache_key] = True
                    return True
                else:
                    logger.warning(f"⚠️ OpenAI 连接测试失败 (错误码: {result})")
                    LLMFactory._connection_tested[cache_key] = False
                    return False

            elif provider == "openrouter":
                # OpenRouter 使用 HTTPS
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex(("openrouter.ai", 443))
                sock.close()

                if result == 0:
                    logger.info("✅ OpenRouter 连接测试通过")
                    LLMFactory._connection_tested[cache_key] = True
                    return True
                else:
                    logger.warning(f"⚠️ OpenRouter 连接测试失败 (错误码: {result})")
                    LLMFactory._connection_tested[cache_key] = False
                    return False

            else:
                # 其他 provider 默认返回 True
                logger.info(f"⏭️ 跳过连接测试: {provider}")
                return True

        except Exception as e:
            logger.warning(f"⚠️ 连接测试异常 ({provider}): {e}")
            LLMFactory._connection_tested[cache_key] = False
            return False

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
        """
        创建 Provider 客户端

        Args:
            provider: Provider 名称
            settings: 配置对象
            model_override: 可选的模型名称

        Returns:
            LLM 客户端实例

        Raises:
            ValueError: 如果 provider 不支持
        """
        # 从注册表获取 Provider 类
        provider_class = LLMFactory.PROVIDER_REGISTRY.get(provider)

        if provider_class is None:
            supported = ", ".join(LLMFactory.PROVIDER_REGISTRY.keys())
            raise ValueError(
                f"Unsupported LLM provider: {provider}. "
                f"Supported providers: {supported}"
            )

        # 创建 Provider 实例并生成客户端
        provider_instance = provider_class(settings)
        return provider_instance.create_client(model_override=model_override)


# LLM 客户端单例
_llm_instance: Optional[Any] = None


def get_llm(
    provider: Optional[str] = None,
    force_new: bool = False,
    skip_connection_test: bool = False,
) -> Any:
    """
    获取 LLM 客户端单例。

    参数：
        provider: LLM 提供商（可选）
        force_new: 强制创建新实例（默认使用单例）
        skip_connection_test: 跳过连接测试（默认 False）
    """
    global _llm_instance

    if _llm_instance is None or force_new:
        settings = get_settings()

        if not settings.validate_llm_config():
            raise ValueError(
                f"LLM configuration is invalid for provider: {settings.DEFAULT_LLM_PROVIDER}. "
                f"Please check your .env file."
            )

        # 快速连接测试（只测试地址和端口，不发送消息）
        target_provider = provider or settings.DEFAULT_LLM_PROVIDER
        should_test = not skip_connection_test and not getattr(settings, 'LLM_SKIP_CONNECTION_TEST', False)
        if should_test:
            logger.info(f"🔍 开始快速连接测试: provider={target_provider}")
            test_result = LLMFactory.quick_test_connection(target_provider, settings)
            if not test_result:
                logger.warning(
                    f"⚠️ LLM 连接测试失败（provider={target_provider}），"
                    f"但仍会尝试创建客户端（可能连接会在实际调用时恢复）"
                )
            else:
                logger.info(f"✅ LLM 连接测试通过: provider={target_provider}")

        _llm_instance = LLMFactory.create_llm(provider=provider, settings=settings)
        logger.info("LLM client initialized successfully")

    return _llm_instance


def reset_llm():  # type: ignore[no-untyped-def]
    """
    重置 LLM 单例（用于测试）。
    """
    global _llm_instance
    _llm_instance = None
    LLMFactory._client_cache.clear()


# 导出
__all__ = [
    "LLMFactory",
    "reset_llm",
    "get_llm",
]
