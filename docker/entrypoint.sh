#!/bin/bash
set -e

# ============================================================================
# Ops Agent Docker Entrypoint
# 功能：环境检查、数据库初始化、启动服务
# ============================================================================

echo "=========================================="
echo "  Ops Agent v4.0 - Starting..."
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ============================================================================
# 1. 环境检查
# ============================================================================
log_info "检查环境变量..."

# 检查必要的环境变量
required_vars=(
    "DATABASE_URL"
    "JWT_SECRET_KEY"
)

missing_vars=()
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -gt 0 ]; then
    log_error "缺少必要的环境变量: ${missing_vars[*]}"
    log_info "请设置以下环境变量后重试："
    for var in "${missing_vars[@]}"; do
        echo "  - $var"
    done
    exit 1
fi

# 检查 LLM 配置
if [ -z "$DEFAULT_LLM_PROVIDER" ]; then
    log_warn "DEFAULT_LLM_PROVIDER 未设置，使用默认值: openai"
    export DEFAULT_LLM_PROVIDER=openai
fi

# 根据 LLM 提供商检查 API Key
case "$DEFAULT_LLM_PROVIDER" in
    openai)
        if [ -z "$OPENAI_API_KEY" ]; then
            log_error "使用 OpenAI 但未设置 OPENAI_API_KEY"
            exit 1
        fi
        ;;
    claude)
        if [ -z "$CLAUDE_API_KEY" ]; then
            log_error "使用 Claude 但未设置 CLAUDE_API_KEY"
            exit 1
        fi
        ;;
    zhipu)
        if [ -z "$ZHIPU_API_KEY" ]; then
            log_error "使用智谱 AI 但未设置 ZHIPU_API_KEY"
            exit 1
        fi
        ;;
    openrouter)
        if [ -z "$OPENROUTER_API_KEY" ]; then
            log_error "使用 OpenRouter 但未设置 OPENROUTER_API_KEY"
            exit 1
        fi
        ;;
esac

log_info "环境变量检查通过"

# ============================================================================
# 2. 数据目录准备
# ============================================================================
log_info "准备数据目录..."

# 确保数据目录存在
mkdir -p /app/workspace/data
mkdir -p /app/workspace/logs
mkdir -p /app/workspace/checkpoints

# 设置权限
chmod -R 755 /app/workspace

log_info "数据目录准备完成"

# ============================================================================
# 3. 数据库初始化
# ============================================================================
log_info "检查数据库状态..."

# 检查是否需要初始化
DB_FILE="/app/workspace/data/ops_agent_v2.db"
INIT_FLAG="/app/workspace/data/.initialized"

if [ ! -f "$INIT_FLAG" ]; then
    log_info "首次启动，执行数据库初始化..."

    # 运行初始化脚本
    cd /app

    # 使用 Python 执行初始化
    python -c "
import sys
sys.path.insert(0, '/app')
from scripts.init import create_tables, init_admin_user, sync_tools_and_approval, init_system_settings, seed_default_prompts
from app.utils.logger import get_logger

logger = get_logger('init')

try:
    logger.info('开始数据库初始化...')
    create_tables(reset=False)
    init_admin_user()
    sync_tools_and_approval()
    init_system_settings()
    seed_default_prompts()
    logger.info('数据库初始化完成!')
except Exception as e:
    logger.error(f'初始化失败: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
"

    if [ $? -eq 0 ]; then
        # 创建初始化标志
        touch "$INIT_FLAG"
        log_info "数据库初始化成功"
    else
        log_error "数据库初始化失败"
        exit 1
    fi
else
    log_info "数据库已初始化，跳过"
fi

# ============================================================================
# 4. K8s 配置检查（可选）
# ============================================================================
if [ "$K8S_ENABLED" = "true" ]; then
    log_info "K8s 集成已启用"

    # 检查 kubeconfig
    if [ -n "$KUBECONFIG" ] && [ -f "$KUBECONFIG" ]; then
        log_info "使用自定义 kubeconfig: $KUBECONFIG"
    elif [ -f "/root/.kube/config" ]; then
        log_info "使用默认 kubeconfig: /root/.kube/config"
    else
        log_warn "未找到 kubeconfig，K8s 功能可能无法正常工作"
    fi

    # 测试 kubectl 连接
    if command -v kubectl &> /dev/null; then
        if kubectl cluster-info &> /dev/null; then
            log_info "kubectl 连接测试成功"
        else
            log_warn "kubectl 无法连接到集群"
        fi
    fi
else
    log_info "K8s 集成未启用"
fi

# ============================================================================
# 5. 启动服务
# ============================================================================
log_info "启动 Ops Agent 服务..."
echo ""

# 显示配置摘要
echo "=========================================="
echo "  配置摘要"
echo "=========================================="
echo "  LLM Provider: $DEFAULT_LLM_PROVIDER"
echo "  Database: $DATABASE_URL"
echo "  K8s Enabled: ${K8S_ENABLED:-false}"
echo "  Feishu Enabled: ${FEISHU_ENABLED:-false}"
echo "  Debug Mode: ${DEBUG:-false}"
echo "=========================================="
echo ""

# 执行传入的命令
exec "$@"
