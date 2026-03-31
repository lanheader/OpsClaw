FROM lanjiaxuan/ops-tools:v2025103003

LABEL maintainer="lanjiaxuan"
LABEL version="4.0.0"
LABEL description="OpsClaw - Intelligent Operations Automation Platform"

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装 UV（Python 包管理器）
RUN pip install uv

# 复制依赖文件
COPY pyproject.toml ./

# 使用 UV 安装依赖
RUN uv pip install --system -e .

# 复制应用代码
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY config/ ./config/

# 创建数据目录
RUN mkdir -p /app/data /app/workspace/data /app/workspace/logs

# 复制入口脚本
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 入口点
ENTRYPOINT ["/entrypoint.sh"]

# 默认命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
