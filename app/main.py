# app/main.py
"""FastAPI application entry point for ops-agent-langgraph"""

import logging
import sys
import os
from contextlib import asynccontextmanager

# ============ 第一优先级：尽早抑制噪音日志（在任何导入之前）============
# 很多第三方库在导入时就输出 DEBUG 日志，需要尽早抑制

# 设置 LiteLLM 日志级别（通过环境变量）
os.environ.setdefault("LITELLM_LOG", "WARNING")

# 设置根日志级别为 WARNING，避免导入时的噪音
logging.getLogger().setLevel(logging.WARNING)

# 抑制特定库的日志
for _noisy in ("litellm", "litellm_logging", "app.tools.base", "app.tools"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# ============ 第二优先级：日志系统初始化============
# 检查是否使用 loguru（默认启用）
USE_LOGURU = os.getenv("USE_LOGURU", "true").lower() == "true"

logger = None  # 初始化 logger 变量

if USE_LOGURU:
    try:
        from app.utils.loguru_config import setup_logging as setup_loguru, logger as loguru_logger
        setup_loguru()
        logger = loguru_logger
    except ImportError:
        USE_LOGURU = False

# 如果不使用 loguru，使用标准 logging 配置
if not USE_LOGURU or logger is None:
    # 先临时设置一个简单的日志配置，避免导入时的噪音
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

# ============ 第二优先级：导入配置 ============
from app.core.config import get_settings
settings = get_settings()

# ============ 第三优先级：导入其他模块 ============
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import auth
from app.api.v1 import feishu
from app.api.v1 import integrations
from app.api.v1 import llm
from app.api.v1 import permissions
from app.api.v1 import roles
from app.api.v1 import settings as settings_api
from app.api.v1 import users
from app.api.v1 import approval_config
from app.api.v2 import alert
from app.api.v2 import chat
from app.api.v2 import inspection
from app.api.v2 import workflow
from app.api.v2 import knowledge_base
from app.api.v2 import messaging
from app.core.llm_factory import LLMFactory
from app.deepagents.main_agent import get_ops_agent as _init_ops_agent
from app.utils.logger import RequestContextFilter, ContextFormatter

# ============ 完善日志系统配置 ============
# 在所有模块导入后，完善日志配置

if USE_LOGURU:
    # Loguru 已经在前面设置好了
    logger.info("🚀 应用启动 - 使用 Loguru 日志系统")
else:
    # 完善标准 logging 配置（带请求上下文支持）
    from app.utils.logger import _suppress_third_party_logs
    _suppress_third_party_logs()

    # 创建根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL))

    # 清除之前的临时 handler
    root_logger.handlers.clear()

    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, settings.LOG_LEVEL))

    # 添加请求上下文过滤器
    context_filter = RequestContextFilter()
    console_handler.addFilter(context_filter)

    # 使用自定义格式化器（包含 session_id 和 request_id）
    formatter = ContextFormatter(
        "%(asctime)s - [%(session_id)s] - [%(request_id)s] - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)

    # 添加处理器到根日志记录器
    root_logger.addHandler(console_handler)

    logger = logging.getLogger(__name__)

# 压制第三方库的 DEBUG 噪音，只保留 WARNING 及以上
for _noisy_logger in (
    "aiosqlite",
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "httpx",
    "httpcore",
    "urllib3",
    "asyncio",
    "hpack",
    "h2",
    "langchain_core.messages.ai",  # 压制 "Failed to parse tool calls" DEBUG 日志
    "openai",  # 压制 OpenAI 客户端的 DEBUG 日志
    "openai._base_client",
    "openai._client",
    "langchain",
    "langchain_core",
    "langsmith",
    "langgraph",
    "kubernetes",
    "kubernetes.client",
    "litellm",  # 压制 LiteLLM 的 DEBUG 日志
    "litellm_logging",
    "app.tools.base",  # 抑制工具注册的 DEBUG 日志
    "app.tools",
):
    logging.getLogger(_noisy_logger).setLevel(logging.WARNING)

# Global DeepAgents instance (managed by main_agent.py singleton)
_ops_agent = None


async def initialize_deepagents():
    """初始化 DeepAgents 主智能体（异步）"""
    global _ops_agent

    logger.info("🔧 初始化 DeepAgents 主智能体...")

    try:
        # 获取 Ops Agent 单例（主智能体 + 6 个子智能体 + 中间件）
        _ops_agent = await _init_ops_agent(enable_approval=True)

        logger.info("✅ DeepAgents 主智能体初始化成功")
        logger.info("  - 主智能体: Ops Agent (单例模式)")
        logger.info(
            "  - 子智能体: intent-agent, data-agent, analyze-agent, execute-agent, report-agent, format-agent"
        )
        logger.info("  - 中间件: MessageTrimmingMiddleware, LoggingMiddleware")
        logger.info("  - 会话管理: LangGraph SQLite checkpointer (持久化)")

    except Exception as e:
        logger.error(f"❌ Failed to initialize DeepAgents: {e}")
        raise


def get_ops_agent():
    """获取全局 Ops Agent 实例"""
    global _ops_agent
    if _ops_agent is None:
        raise RuntimeError("DeepAgents not initialized. Call initialize_deepagents() first.")
    return _ops_agent


async def cleanup_deepagents():
    """清理 DeepAgents 资源（异步）"""
    global _ops_agent

    if _ops_agent is not None:
        logger.info("🧹 清理 DeepAgents 资源...")

        try:
            # 清理检查点器（如果存在）
            if hasattr(_ops_agent, 'checkpointer'):
                checkpointer = _ops_agent.checkpointer
                if hasattr(checkpointer, 'close'):
                    await checkpointer.close()
                    logger.info("✅ 检查点器已关闭")

            # 清理 agent 本身（如果支持）
            if hasattr(_ops_agent, 'aclose'):
                await _ops_agent.aclose()
                logger.info("✅ Agent 已关闭")

            # 重置全局变量
            _ops_agent = None
            logger.info("✅ DeepAgents 资源清理完成")

        except Exception as e:
            logger.error(f"❌ 清理 DeepAgents 时出错: {e}")
            # 即使出错也要重置，避免保留可能损坏的引用
            _ops_agent = None
    else:
        logger.info("ℹ️  DeepAgents 未初始化，无需清理")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""

    # Startup
    logger.info("🚀 Starting Ops Agent (DeepAgents Architecture v3.0)")
    logger.info(f"Environment: {settings.SECURITY_ENVIRONMENT}")
    logger.info(f"LLM Provider: {settings.DEFAULT_LLM_PROVIDER}")

    # Initialize DeepAgents
    try:
        await initialize_deepagents()
    except Exception as e:
        logger.error(f"❌ Failed to initialize DeepAgents: {e}")
        logger.warning(
            "Application starting without DeepAgents (some features will be unavailable)"
        )

    # Start Feishu long connection if enabled
    if settings.FEISHU_ENABLED and settings.FEISHU_CONNECTION_MODE in ["longconn", "auto"]:
        logger.info("🔌 Starting Feishu long connection...")

        try:
            from app.integrations.feishu.lark_longconn import start_feishu_longconn
            import asyncio

            start_feishu_longconn(
                app_id=settings.FEISHU_APP_ID,
                app_secret=settings.FEISHU_APP_SECRET,
                main_loop=asyncio.get_event_loop(),
            )
            logger.info("✅ Feishu long connection started successfully")

        except Exception as e:
            logger.error(f"❌ Failed to start Feishu long connection: {e}")

            if settings.FEISHU_CONNECTION_MODE == "longconn":
                raise
            else:
                logger.warning("⚠️  Falling back to Webhook mode")

    else:
        logger.info(f"ℹ️  Feishu long connection not enabled")

    yield

    # Shutdown
    logger.info("👋 Shutting down Ops Agent")

    # Cleanup DeepAgents resources
    try:
        await cleanup_deepagents()
    except Exception as e:
        logger.error(f"❌ Failed to cleanup DeepAgents: {e}")

    # Stop Feishu long connection (if started)
    if settings.FEISHU_ENABLED and settings.FEISHU_CONNECTION_MODE in ["longconn", "auto"]:
        from app.integrations.feishu.lark_longconn import get_feishu_longconn_client

        logger.info("🔌 Stopping Feishu long connection...")

        client = get_feishu_longconn_client()
        if client:
            client.stop()
            logger.info("✅ Feishu long connection stopped")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="Intelligent Operations Automation Platform with DeepAgents - v3.0 Architecture",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
)


# 【调试】添加全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常捕获和日志记录"""
    logger.error(f"🔥 全局异常捕获")
    logger.error(f"   请求路径: {request.url.path}")
    logger.error(f"   请求方法: {request.method}")
    logger.error(f"   异常类型: {type(exc).__name__}")
    logger.error(f"   异常信息: {str(exc)}")
    logger.error(f"   堆栈跟踪:", exc_info=True)

    return JSONResponse(status_code=500, content={"detail": f"Internal server error: {str(exc)}"})


# Configure CORS
if settings.ENABLE_CORS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS if settings.CORS_ORIGINS else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Register API routers
app.include_router(workflow.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(inspection.router, prefix="/api/v2")
app.include_router(alert.router, prefix="/api/v2")
app.include_router(knowledge_base.router, prefix="/api")  # 新增：知识库管理

# 统一消息 API（新架构）
if get_settings().USE_NEW_MESSAGING_ARCH:
    try:
        from app.integrations.messaging.registry import initialize_channels
        initialize_channels()  # 初始化渠道适配器
        app.include_router(messaging.router, prefix="/api/v2/messaging")
        logger.info("✅ 新消息架构已启用")
    except Exception as e:
        logger.warning(f"⚠️ 新消息架构初始化失败: {e}，回退到旧架构")

# 飞书 API（兼容层，重定向到新架构）
app.include_router(feishu.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(permissions.router, prefix="/api/v1")
app.include_router(roles.router, prefix="/api/v1")
app.include_router(settings_api.router, prefix="/api/v1")
app.include_router(llm.router, prefix="/api/v1")
app.include_router(integrations.router, prefix="/api/v1")
# 工具权限管理 API
from app.api.v1 import tools
app.include_router(tools.router, prefix="/api/v1")
# 审批配置管理 API
app.include_router(approval_config.router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint"""
    agent_status = "initialized" if _ops_agent is not None else "not_initialized"

    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "version": "3.0.0",
        "architecture": "DeepAgents Multi-Agent System",
        "docs": "/docs" if settings.ENABLE_DOCS else "disabled",
        "status": "Running",
        "llm_provider": settings.DEFAULT_LLM_PROVIDER,
        "agent_status": agent_status,
    }


@app.get("/api/v1/health")
@app.get("/api/v2/health")
async def health():
    """Health check endpoint"""
    llm_status = "unknown"
    try:
        # 使用默认 LLM provider（不再使用 profile）
        llm = LLMFactory.create_llm()
        llm_status = f"available:{type(llm).__name__}"
    except Exception as e:
        llm_status = f"unavailable: {str(e)}"

    agent_status = "initialized" if _ops_agent is not None else "not_initialized"

    return {
        "status": "healthy",
        "version": "3.0.0",
        "architecture": "deepagents",
        "llm_status": llm_status,
        "agent_status": agent_status,
    }
