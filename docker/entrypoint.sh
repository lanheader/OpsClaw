#!/bin/bash
set -e

echo "=========================================="
echo "  OpsClaw v4.0 - Starting..."
echo "=========================================="

# PATH is already set by Dockerfile to include /app/.venv/bin
# Just verify Python is available
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 not found in PATH"
    exit 1
fi

# ============================================================================
# 1. 数据目录
# ============================================================================
mkdir -p /app/workspace/data /app/workspace/logs

# 设置默认 DATABASE_URL（如果未设置）
export DATABASE_URL="${DATABASE_URL:-sqlite:///./workspace/data/ops_agent_v2.db}"

# ============================================================================
# 2. 数据库初始化（仅首次启动）
# ============================================================================
INIT_FLAG="/app/workspace/data/.initialized"

if [ ! -f "$INIT_FLAG" ]; then
    echo "[INFO] 首次启动，执行数据库初始化..."
    cd /app && python3 scripts/init.py --skip-kb
    if [ $? -eq 0 ]; then
        touch "$INIT_FLAG"
        echo "[INFO] 数据库初始化成功"
    else
        echo "[ERROR] 数据库初始化失败"
        exit 1
    fi
else
    echo "[INFO] 数据库已初始化，跳过"
fi

# ============================================================================
# 3. 启动 Supervisord（管理 Nginx + Uvicorn）
# ============================================================================
echo "=========================================="
echo "  LLM Provider: ${DEFAULT_LLM_PROVIDER:-openai}"
echo "  Database: ${DATABASE_URL}"
echo "  K8s Enabled: ${K8S_ENABLED:-false}"
echo "  Feishu Enabled: ${FEISHU_ENABLED:-false}"
echo "=========================================="

# 启动 supervisord（前台 + 后端）
exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
