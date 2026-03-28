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

    # ========== Server Configuration ==========
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = False

    # ========== Application ==========
    APP_NAME: str = "Ops Agent LangGraph"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ========== Database ==========
    DATABASE_URL: str = "sqlite:///./data/ops_agent_v2.db"
    CHECKPOINT_DB_URL: str = "sqlite:///./data/ops_checkpoints.db"

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

    # 飞书聊天模式配置
    FEISHU_CHAT_MODE: str = Field(
        default="command_only",
        description="飞书聊天模式: ai_chat (AI对话) 或 command_only (仅指令)",
    )
    FEISHU_REJECT_MESSAGE: str = Field(
        default="有事说事，没事退朝，运维AI，拒绝闲聊",
        description="command_only 模式下对非指令消息的回复",
    )

    # 意图分类配置
    FEISHU_ENABLE_INTENT_CLASSIFICATION: bool = Field(
        default=True, description="是否启用意图分类 Agent（仅在 ai_chat 模式下生效）"
    )
    FEISHU_INTENT_THRESHOLD: float = Field(
        default=0.5, ge=0.0, le=1.0, description="意图相关性阈值 (0-1)，高于此值才会响应"
    )

    # ========== 消息渠道架构配置 ==========
    USE_NEW_MESSAGING_ARCH: bool = Field(
        default=False,
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
    SECURITY_POLICY_PATH: str = "./config/security_policy.yaml"
    SECURITY_ENVIRONMENT: str = "production"

    # ========== JWT 配置 ==========
    JWT_SECRET_KEY: str = Field(default="your-secret-key-here-change-in-production", min_length=32)
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_ACCESS_TOKEN_EXPIRE_DAYS: int = 7

    # ========== 初始管理员账号 ==========
    INITIAL_ADMIN_USERNAME: str = "admin"
    INITIAL_ADMIN_PASSWORD: str = "admin123"
    INITIAL_ADMIN_EMAIL: str = "admin@ops-agent.local"

    # ========== Feature Flags ==========
    DEFAULT_WORKFLOW_VERSION: str = "v1"
    V2_INSPECTION_ENABLED: bool = False
    V2_HEALING_ENABLED: bool = False
    V2_SECURITY_ENABLED: bool = True
    V2_PLUGINS: str = ""

    # ========== API & CORS ==========
    ENABLE_DOCS: bool = False
    ENABLE_CORS: bool = False
    CORS_ORIGINS: List[str] = []

    # ========== Performance ==========
    WORKERS: int = 4
    TIMEOUT: int = 120

    # ========== Mock Data ==========
    USE_MOCK_DATA: bool = False

    # ========== Subagent LLM Configuration ==========
    SUBAGENT_INTENT_MODEL: str = Field(default="glm-4-flash", description="意图识别子智能体使用的模型")
    SUBAGENT_ANALYZE_MODEL: str = Field(default="glm-4", description="分析决策子智能体使用的模型")
    SUBAGENT_DATA_MODEL: str = Field(default="glm-4", description="数据采集子智能体使用的模型")
    SUBAGENT_EXECUTE_MODEL: str = Field(default="glm-4", description="执行操作子智能体使用的模型")
    SUBAGENT_REPORT_MODEL: str = Field(default="glm-4", description="报告生成子智能体使用的模型")
    SUBAGENT_FORMAT_MODEL: str = Field(default="glm-4-flash", description="响应格式化子智能体使用的模型")

    # ========== 记忆系统配置 ==========
    ENABLE_VECTOR_MEMORY: bool = Field(default=True, description="是否启用向量记忆（ChromaDB），False 则使用 SQLite FTS5 关键词记忆")

    # ========== Mem0 记忆系统配置 ==========
    MEM0_ENABLED: bool = Field(default=True, description="是否启用 Mem0 通用对话记忆")
    MEM0_API_KEY: Optional[str] = Field(default=None, description="Mem0 Platform API Key（使用托管服务，留空则自托管）")
    MEM0_PROVIDER: Optional[str] = Field(default=None, description="Mem0 使用的 LLM 提供商（留空则使用 DEFAULT_LLM_PROVIDER）")
    MEM0_MODEL: Optional[str] = Field(default=None, description="Mem0 使用的模型（留空则使用对应 provider 的默认模型）")
    MEM0_AUTO_LEARN: bool = Field(default=True, description="是否自动从对话中学习")

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

    def get_v2_plugins_list(self) -> List[str]:
        """获取 v2 插件列表。"""
        if not self.V2_PLUGINS:
            return []
        return [p.strip() for p in self.V2_PLUGINS.split(",") if p.strip()]

    def get_subagent_model(self, subagent_name: str) -> str:
        """返回指定 subagent 的模型配置。"""
        mapping = {
            "intent-agent": self.SUBAGENT_INTENT_MODEL,
            "analyze-agent": self.SUBAGENT_ANALYZE_MODEL,
            "data-agent": self.SUBAGENT_DATA_MODEL,
            "execute-agent": self.SUBAGENT_EXECUTE_MODEL,
            "report-agent": self.SUBAGENT_REPORT_MODEL,
            "format-agent": self.SUBAGENT_FORMAT_MODEL,
        }
        return mapping.get(subagent_name, self.SUBAGENT_INTENT_MODEL)


# 单例实例
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """获取单例配置实例。"""
    global _settings

    if _settings is None:
        _settings = Settings()

    return _settings
