# Ops Agent Dockerfile
# 多阶段构建：前端构建 + Python 后端 + Nginx

# ============================================================
# Stage 1: 构建前端
# ============================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# 复制 package 文件
COPY frontend/package*.json ./

# 安装依赖
RUN npm ci

# 复制源代码
COPY frontend/ ./

# 构建生产版本
RUN npm run build

# ============================================================
# Stage 2: Python 后端 + Nginx 运行时
# ============================================================
FROM lanjiaxuan/ops-tools:v2025103003

LABEL maintainer="lanjiaxuan"

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv python3-dev \
        nginx supervisor curl bash && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 创建虚拟环境
RUN python3 -m venv /app/.venv

# 设置环境变量
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# 安装 UV 和基础工具
RUN pip install uv setuptools wheel

# 复制后端代码
COPY app/ /app/app/
COPY pyproject.toml pyproject.toml
COPY scripts/ /app/scripts/
COPY docker/ /app/docker/

# 安装 Python 依赖
RUN uv pip install ".[kubernetes,prometheus]"

# 从 Stage 1 复制前端构建产物到 Nginx 目录
COPY --from=frontend-builder /app/frontend/dist /usr/share/nginx/html

# 复制 Nginx 和 Supervisord 配置
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# 创建数据目录
RUN mkdir -p /app/workspace/data /app/workspace/logs

# 设置入口脚本权限
RUN chmod +x /app/docker/entrypoint.sh

# 暴露端口 (Nginx)
EXPOSE 80

# 健康检查（通过 Nginx 访问后端 API）
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost/api/v1/health || exit 1

# 入口点
ENTRYPOINT ["/app/docker/entrypoint.sh"]

# 默认命令：启动 supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]
