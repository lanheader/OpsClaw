# OpsClaw Dockerfile
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
        python3 python3-dev \
        nginx supervisor curl bash && \
    rm -rf /var/lib/apt/lists/*

# 从官方镜像复制 uv 二进制（无需 pip 安装）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# 设置环境变量
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 复制依赖文件（利用 Docker 层缓存：依赖未变时跳过安装）
COPY pyproject.toml uv.lock /app/

# 安装 Python 依赖（--no-install-project 仅装依赖，不装项目本身）
RUN uv sync --frozen --no-install-project --extra kubernetes --extra prometheus

# 复制后端代码
COPY app/ /app/app/
COPY scripts/ /app/scripts/
COPY docker/ /app/docker/

# 安装项目本身（不重装依赖）
RUN uv sync --frozen --extra kubernetes --extra prometheus

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
