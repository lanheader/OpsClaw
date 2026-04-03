# app/core/config.py
"""应用配置管理"""

from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置类。

    从环境变量或 .env 文件加载配置。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # ========== Application ==========
    APP_NAME: str = "OpsClaw LangGraph"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ========== Database ==========
    DATABASE_URL: str = "sqlite:///./workspace/data/ops_agent_v2.db"
    CHECKPOINT_DB_URL: str = "sqlite:///./workspace/data/ops_checkpoints.db"

    # ========== LLM Provider ==========
    DEFAULT_LLM_PROVIDER: str = Field(default="openai", description="openai, claude, ollama, zhipu, openrouter")

    # OpenRouter
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = "anthropic/claude-3.5-sonnet"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_TEMPERATURE: float = 0.0
    OPENROUTER_MAX_TOKENS: int = 4096
    OPENROUTER_REQUEST_TIMEOUT: int = 120

    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4-turbo-preview"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_TEMPERATURE: float = 0.0
    OPENAI_MAX_TOKENS: int = 4096
    OPENAI_REQUEST_TIMEOUT: int = 120

    # Claude
    CLAUDE_API_KEY: Optional[str] = None
    CLAUDE_MODEL: str = "claude-3-sonnet-20240229"
    CLAUDE_TEMPERATURE: float = 0.0
    CLAUDE_MAX_TOKENS: int = 4096
    CLAUDE_REQUEST_TIMEOUT: int = 120

    # 智谱 AI (ZhipuAI)
    ZHIPU_API_KEY: Optional[str] = None
    ZHIPU_MODEL: str = "glm-4"
    ZHIPU_TEMPERATURE: float = 0.0
    ZHIPU_MAX_TOKENS: int = 4096
    ZHIPU_REQUEST_TIMEOUT: int = 120

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "mistral"
    OLLAMA_TEMPERATURE: float = 0.0

    # LLM 连接测试
    LLM_SKIP_CONNECTION_TEST: bool = Field(
        default=False,
        description="跳过 LLM 连接测试（只测试地址和端口，不发送消息）"
    )

    # ========== Feishu Integration ==========
    FEISHU_ENABLED: bool = False
    FEISHU_APP_ID: Optional[str] = None
    FEISHU_APP_SECRET: Optional[str] = None
    FEISHU_WEBHOOK_URL: Optional[str] = None
    FEISHU_VERIFICATION_TOKEN: Optional[str] = None
    FEISHU_CHAT_ID: Optional[str] = None
    FEISHU_ENCRYPT_KEY: Optional[str] = None
    FEISHU_TEST_CHAT_ID: Optional[str] = Field(
        default=None,
        description="测试消息发送的目标 chat_id"
    )
    FEISHU_CONNECTION_MODE: str = "auto"
    FEISHU_LONG_CONNECTION_ENABLED: bool = Field(
        default=True,
        description="是否启用飞书长连接模式"
    )
    FEISHU_WEBHOOK_REQUIRE_MENTION: bool = Field(
        default=True,
        description="Webhook 模式下是否需要 @机器人才触发"
    )
    FEISHU_REPLY_WITH_MENTION: bool = Field(
        default=True,
        description="回复消息时是否 @用户"
    )
    FEISHU_LONGCONN_HEARTBEAT_INTERVAL: int = 30
    FEISHU_LONGCONN_RECONNECT_INTERVAL: int = 5
    FEISHU_LONGCONN_MAX_RECONNECT_ATTEMPTS: int = 10

    # ========== 消息渠道架构配置 ==========
    USE_NEW_MESSAGING_ARCH: bool = Field(
        default=True,
        description="是否使用新的消息渠道抽象架构（True=新架构, False=旧 callback.py）"
    )

    # ========== Prometheus ==========
    PROMETHEUS_ENABLED: bool = False
    PROMETHEUS_URL: Optional[str] = None

    # ========== Loki ==========
    LOKI_ENABLED: bool = False
    LOKI_URL: Optional[str] = None

    # ========== Kubernetes ==========
    K8S_ENABLED: bool = False
    KUBECONFIG: Optional[str] = None

    # ========== Security Policy ==========
    SECURITY_ENVIRONMENT: str = "production"

    # ========== JWT 配置 ==========
    JWT_SECRET_KEY: str = Field(default="your-secret-key-here-change-in-production", min_length=32)
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_ACCESS_TOKEN_EXPIRE_DAYS: int = 7

    # ========== 初始管理员账号 ==========
    INITIAL_ADMIN_PASSWORD: str = "admin123"

    # ========== API & CORS ==========
    ENABLE_DOCS: bool = False
    ENABLE_CORS: bool = False
    CORS_ORIGINS: List[str] = []

    # ========== Subagent LLM Configuration ==========
    SUBAGENT_DATA_MODEL: str = Field(default="glm-4", description="数据采集子智能体使用的模型")
    SUBAGENT_ANALYZE_MODEL: str = Field(default="glm-4", description="分析诊断子智能体使用的模型")
    SUBAGENT_EXECUTE_MODEL: str = Field(default="glm-4", description="执行操作子智能体使用的模型")
    SUBAGENT_NETWORK_MODEL: str = Field(default="glm-4", description="网络诊断子智能体使用的模型")
    SUBAGENT_SECURITY_MODEL: str = Field(default="glm-4", description="安全巡检子智能体使用的模型")
    SUBAGENT_STORAGE_MODEL: str = Field(default="glm-4", description="存储排查子智能体使用的模型")

    def get_checkpoint_db_url(self) -> str:
        """返回 LangGraph checkpoint 使用的数据库 URL（独立数据库文件）。"""
        return self.CHECKPOINT_DB_URL

    def validate_llm_config(self) -> bool:
        """验证 LLM 配置是否有效。"""
        if self.DEFAULT_LLM_PROVIDER == "openai":
            return self.OPENAI_API_KEY is not None
        elif self.DEFAULT_LLM_PROVIDER == "claude":
            return self.CLAUDE_API_KEY is not None
        elif self.DEFAULT_LLM_PROVIDER == "zhipu":
            return self.ZHIPU_API_KEY is not None
        elif self.DEFAULT_LLM_PROVIDER == "ollama":
            return True
        elif self.DEFAULT_LLM_PROVIDER == "openrouter":
            return self.OPENROUTER_API_KEY is not None
        return False

    def get_subagent_model(self, subagent_name: str) -> str:
        """返回指定 subagent 的模型配置。"""
        mapping = {
            "data-agent": self.SUBAGENT_DATA_MODEL,
            "analyze-agent": self.SUBAGENT_ANALYZE_MODEL,
            "execute-agent": self.SUBAGENT_EXECUTE_MODEL,
            "network-agent": self.SUBAGENT_NETWORK_MODEL,
            "security-agent": self.SUBAGENT_SECURITY_MODEL,
            "storage-agent": self.SUBAGENT_STORAGE_MODEL,
        }
        return mapping.get(subagent_name, self.SUBAGENT_DATA_MODEL)


# 单例实例
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """获取单例配置实例。"""
    global _settings

    if _settings is None:
        _settings = Settings()

    return _settings
