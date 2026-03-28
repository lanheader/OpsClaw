"""
记忆增强的 LLM 工厂类

支持：
- 创建 LLM 客户端（多个提供商）
- 创建 Embedding 客户端（向量检索）
"""

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from typing import Any, Dict, Optional, List, cast
import logging
import httpx
import socket

from app.core.config import Settings, get_settings

# 尝试导入可选依赖
try:
    from langchain_anthropic import ChatAnthropic
except ImportError:
    ChatAnthropic = None  # type: ignore

try:
    from langchain_community.chat_models import ChatZhipuAI
except ImportError:
    ChatZhipuAI = None  # type: ignore

logger = logging.getLogger(__name__)


class LLMFactory:
    """
    LLM 工厂类。

    根据配置创建不同的 LLM 客户端（OpenAI, Claude, ZhipuAI, Ollama, OpenRouter）。
    """

    _client_cache: Dict[str, Any] = {}
    _connection_tested: Dict[str, bool] = {}  # 缓存连接测试结果

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
                    port = int(port)
                else:
                    host = host_port
                    port = 11434  # Ollama 默认端口

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
    def _annotate_llm_client(client: BaseChatModel, provider: str, model_name: str) -> BaseChatModel:
        """为 LLM 客户端挂载诊断元数据，便于中间件记录真实 provider/model。"""
        setattr(client, "_ops_provider", provider)
        setattr(client, "_ops_model", model_name)
        return client

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
        client = cast(Any, ChatOpenAI)(**openai_kwargs)
        return LLMFactory._annotate_llm_client(client, "openai", model_name)

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
        if ChatAnthropic is None:
            raise ImportError(
                "langchain-anthropic is not installed. "
                "Please install it with: pip install langchain-anthropic"
            )

        if not settings.CLAUDE_API_KEY:
            raise ValueError(
                "CLAUDE_API_KEY is not configured. "
                "Please set it in .env file or environment variables."
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
        client = cast(Any, ChatAnthropic)(**claude_kwargs)
        return LLMFactory._annotate_llm_client(client, "claude", model_name)

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
        if ChatZhipuAI is None:
            raise ImportError(
                "langchain-community with ZhipuAI support is not installed. "
                "Please install it with: pip install langchain-community"
            )

        if not settings.ZHIPU_API_KEY:
            raise ValueError(
                "ZHIPU_API_KEY is not configured. "
                "Please set it in .env file or environment variables."
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
        client = cast(Any, ChatZhipuAI)(**zhipu_kwargs)
        return LLMFactory._annotate_llm_client(client, "zhipu", model_name)

    @staticmethod
    def _create_ollama_llm(
        settings: Settings, model_override: Optional[str] = None
    ) -> BaseChatModel:
        """
        创建 Ollama LLM 客户端（本地部署）。

        使用 Ollama 的 OpenAI 兼容 API 来支持工具调用。
        Ollama 提供 /v1 端点，兼容 OpenAI API 格式。

        参数：
            settings: 配置对象
            model_override: 可选的模型名称，用于覆盖配置中的模型

        返回：
            ChatOpenAI 实例（配置为使用 Ollama 的 OpenAI 兼容端点）

        异常：
            ImportError: 如果 langchain-openai 未安装
        """
        model_name = model_override or settings.OLLAMA_MODEL

        # Ollama 的 OpenAI 兼容端点
        # 例如: http://localhost:11434/v1
        base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"

        logger.info(
            f"Creating Ollama client (OpenAI compatible): model={model_name}, "
            f"base_url={base_url}"
        )

        ollama_kwargs = {
            "model": model_name,
            "temperature": settings.OLLAMA_TEMPERATURE,
            "base_url": base_url,
            "api_key": "ollama",  # Ollama 不需要真实 API key，但 ChatOpenAI 要求提供
            "timeout": 600,  # 大模型推理可能需要更长时间
        }
        client = cast(Any, ChatOpenAI)(**ollama_kwargs)
        return LLMFactory._annotate_llm_client(client, "ollama", model_name)

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
        client = cast(Any, ChatOpenAI)(**openrouter_kwargs)
        return LLMFactory._annotate_llm_client(client, "openrouter", model_name)

    @staticmethod
    def create_embeddings():
        """
        创建 Embedding 模型客户端用于向量检索

        返回：
            支持异步嵌入的客户端

        注意：
            当前使用 OpenAI 的 text-embedding-3-small 模型
            如果 OpenAI 不可用，将返回模拟的零向量生成器
        """
        settings = get_settings()

        # 尝试使用 OpenAI Embeddings
        try:
            if settings.OPENAI_API_KEY:
                logger.info("Creating OpenAI embeddings client")
                return OpenAIEmbeddings(
                    model="text-embedding-3-small",
                    api_key=settings.OPENAI_API_KEY,
                    openai_api_base=settings.OPENAI_BASE_URL
                )
        except Exception as e:
            logger.warning(f"无法创建 OpenAI embeddings: {e}")

        # 尝试使用其他 embedding 模型...
        # TODO: 支持其他 embedding 提供商

        # 返回模拟的 embedding 生成器（用于测试）
        logger.warning("使用模拟 embedding 生成器（向量检索功能受限）")
        return MockEmbeddings()


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


def reset_llm():
    """
    重置 LLM 单例（用于测试）。
    """
    global _llm_instance
    _llm_instance = None
    LLMFactory._client_cache.clear()


class MockEmbeddings:
    """模拟 Embeddings - 用于测试和降级"""

    def __init__(self, dimension: int = 1536):
        self.dimension = dimension

    async def aembed_query(self, text: str) -> List[float]:
        """异步生成（模拟）向量"""
        return [0.0] * self.dimension

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量生成（模拟）向量"""
        return [[0.0] * self.dimension for _ in texts]

    def embed_query(self, text: str) -> List[float]:
        """生成（模拟）向量"""
        return [0.0] * self.dimension


# 导出新的功能
__all__ = [
    "LLMFactory",
    "reset_llm",
    "get_llm",
    "MockEmbeddings",
]
