# Ops Agent (DeepAgents Edition)

<div align="center">

**智能运维自动化平台 - 基于 DeepAgents 框架**

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![DeepAgents](https://img.shields.io/badge/DeepAgents-latest-green)](https://github.com/langchain-ai/deepagents)
[![LangGraph](https://img.shields.io/badge/LangGraph-latest-green)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[English](README_EN.md) | 简体中文

</div>

---

## 📖 项目简介

Ops Agent 是一个基于 **DeepAgents 框架**的智能运维自动化平台，通过主智能体和多个专业化子智能体协同工作，实现从监控、诊断到自愈的全流程自动化。

**当前版本**: v3.0.0 | **工具数量**: 24 个 | **子智能体**: 6 个

### ✨ 核心特性

- 🤖 **DeepAgents 架构**: 主智能体 + 6 个专业子智能体协同工作
- 🎯 **智能任务规划**: 使用 `write_todos` 自动分解复杂任务
- 🔄 **子智能体委派**: 通过 `task()` 工具委派专业任务
- 🛡️ **工具降级机制**: SDK 优先，自动降级到命令行工具（24 个工具，6 个分组）
- 🔐 **中间件架构**: 批准流程、安全审核、智能路由
- 📊 **多渠道接入**: 支持 Web UI 和飞书集成
- 🧠 **会话记忆**: 支持多轮对话和上下文记忆
- 🔒 **动态权限**: 工具权限自动发现，11 个细粒度权限

### 🎯 三大核心场景

1. **交互式集群状态查询** 🔍 - 通过自然语言查询 K8s 集群实时状态
2. **定时巡检报告** 📅 - 按计划自动执行集群巡检，生成健康报告
3. **告警自动诊断与处理** 🚨 - 接收监控告警，自动诊断并提供修复方案

---

## 🚀 快速开始

### 方式一：本地开发环境

#### 1. 环境要求

- Python 3.11+
- Node.js 18+
- UV (Python 包管理器)

#### 2. 克隆项目

```bash
git clone https://github.com/your-org/ops-agent-langgraph.git
cd ops-agent-langgraph
```

#### 3. 安装依赖

```bash
# 使用 UV 安装 Python 依赖（推荐）
uv sync

# 或使用 pip
pip install -e .
```

#### 4. 配置环境变量

```bash
# 复制环境变量示例
cp .env.example .env

# 编辑 .env，配置必要的参数
vim .env
```

**最小配置**：
```bash
# LLM 配置（必须）
DEFAULT_LLM_PROVIDER=zhipu
ZHIPU_API_KEY=your_key_here

# 数据库（必须）
DATABASE_URL=sqlite:///./data/ops_agent_v2.db

# JWT 密钥（必须，生产环境请修改）
JWT_SECRET_KEY=your-secret-key-here-change-in-production
```

#### 5. 初始化数据库

```bash
# 创建数据目录
mkdir -p data

# 初始化数据库（包含 RBAC 表和初始管理员账号）
uv run python scripts/init_auth_db.py
```

#### 6. 启动服务

```bash
# 启动后端服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 启动前端服务（新终端）
cd frontend
npm install
npm run dev
```

#### 7. 访问应用

- **Web UI**: http://localhost:5173
- **API 文档**: http://localhost:8000/docs
- **默认账号**: `admin` / `admin123`

---

### 方式二：Docker 部署（推荐生产环境）

#### 1. 创建 Dockerfile

在项目根目录创建 `Dockerfile`：

```dockerfile
# 多阶段构建 - 前端构建阶段
FROM node:18-alpine AS frontend-builder

WORKDIR /app/frontend

# 复制前端依赖文件
COPY frontend/package*.json ./

# 安装前端依赖
RUN npm ci

# 复制前端源码
COPY frontend/ ./

# 构建前端
RUN npm run build

# 多阶段构建 - 后端运行阶段
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 UV
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# 复制项目文件
COPY pyproject.toml uv.lock ./
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY config/ ./config/
COPY .env.example ./.env

# 安装 Python 依赖
RUN uv sync --frozen

# 复制前端构建产物
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# 创建数据目录
RUN mkdir -p /app/data

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### 2. 创建 docker-compose.yml

在项目根目录创建 `docker-compose.yml`：

```yaml
version: '3.8'  # Docker Compose 格式版本（非项目版本）

services:
  ops-agent:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: ops-agent
    ports:
      - "8000:8000"
    environment:
      # LLM 配置
      - DEFAULT_LLM_PROVIDER=${DEFAULT_LLM_PROVIDER:-zhipu}
      - ZHIPU_API_KEY=${ZHIPU_API_KEY}
      - ZHIPU_MODEL=${ZHIPU_MODEL:-glm-4}

      # 数据库
      - DATABASE_URL=sqlite:///./data/ops_agent_v2.db

      # JWT
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}

      # 飞书配置（可选）
      - FEISHU_ENABLED=${FEISHU_ENABLED:-false}
      - FEISHU_APP_ID=${FEISHU_APP_ID}
      - FEISHU_APP_SECRET=${FEISHU_APP_SECRET}

      # K8s 配置（可选）
      - K8S_ENABLED=${K8S_ENABLED:-false}
      - KUBECONFIG=/app/.kube/config

      # Prometheus 配置（可选）
      - PROMETHEUS_ENABLED=${PROMETHEUS_ENABLED:-false}
      - PROMETHEUS_URL=${PROMETHEUS_URL}

      # Loki 配置（可选）
      - LOKI_ENABLED=${LOKI_ENABLED:-false}
      - LOKI_URL=${LOKI_URL}

      # 安全配置
      - SECURITY_ENVIRONMENT=${SECURITY_ENVIRONMENT:-production}

      # API 配置
      - ENABLE_DOCS=${ENABLE_DOCS:-false}
      - ENABLE_CORS=${ENABLE_CORS:-true}
      - CORS_ORIGINS=${CORS_ORIGINS:-http://localhost:5173}

    volumes:
      # 持久化数据
      - ./data:/app/data
      # K8s 配置（如果需要）
      - ~/.kube:/app/.kube:ro
      # 安全策略配置
      - ./config:/app/config:ro

    restart: unless-stopped

    networks:
      - ops-agent-network

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

networks:
  ops-agent-network:
    driver: bridge
```

#### 3. 创建 .dockerignore

在项目根目录创建 `.dockerignore`：

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.venv/
ENV/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# 测试和覆盖率
.pytest_cache/
.coverage
htmlcov/
.tox/
.hypothesis/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# 环境变量
.env
.env.local
.env.*.local

# 数据库
*.db
*.sqlite
*.sqlite3
data/

# 日志
*.log
logs/

# 前端
frontend/node_modules/
frontend/dist/
frontend/.next/
frontend/out/

# Git
.git/
.gitignore

# 文档
docs/
*.md
!README.md

# 其他
.DS_Store
*.bak
*.tmp
```

#### 4. 构建和启动

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

#### 5. 初始化数据库（首次启动）

```bash
# 进入容器
docker-compose exec ops-agent bash

# 初始化数据库
uv run python scripts/init_auth_db.py

# 退出容器
exit
```

#### 6. 访问应用

- **Web UI**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs（需要在 .env 中设置 `ENABLE_DOCS=true`）
- **默认账号**: `admin` / `admin123`

---

### 方式三：Kubernetes 部署

#### 1. 创建 Kubernetes 部署文件

创建 `k8s/deployment.yaml`：

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: ops-agent

---
apiVersion: v1
kind: ConfigMap
metadata:
  name: ops-agent-config
  namespace: ops-agent
data:
  DATABASE_URL: "sqlite:///./data/ops_agent_v2.db"
  DEFAULT_LLM_PROVIDER: "zhipu"
  SECURITY_ENVIRONMENT: "production"
  ENABLE_CORS: "true"
  CORS_ORIGINS: "http://localhost:5173"

---
apiVersion: v1
kind: Secret
metadata:
  name: ops-agent-secrets
  namespace: ops-agent
type: Opaque
stringData:
  ZHIPU_API_KEY: "your_key_here"
  JWT_SECRET_KEY: "your-secret-key-here-change-in-production"
  FEISHU_APP_ID: "cli_xxxxxxxxxxxxx"
  FEISHU_APP_SECRET: "xxxxxxxxxxxxxxxxxxxxx"

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ops-agent-data
  namespace: ops-agent
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ops-agent
  namespace: ops-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ops-agent
  template:
    metadata:
      labels:
        app: ops-agent
    spec:
      containers:
      - name: ops-agent
        image: your-registry/ops-agent:latest
        ports:
        - containerPort: 8000
          name: http
        envFrom:
        - configMapRef:
            name: ops-agent-config
        - secretRef:
            name: ops-agent-secrets
        volumeMounts:
        - name: data
          mountPath: /app/data
        - name: config
          mountPath: /app/config
          readOnly: true
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 40
          periodSeconds: 30
          timeoutSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 20
          periodSeconds: 10
          timeoutSeconds: 5
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: ops-agent-data
      - name: config
        configMap:
          name: ops-agent-security-config

---
apiVersion: v1
kind: Service
metadata:
  name: ops-agent
  namespace: ops-agent
spec:
  type: ClusterIP
  ports:
  - port: 8000
    targetPort: 8000
    protocol: TCP
    name: http
  selector:
    app: ops-agent

---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ops-agent
  namespace: ops-agent
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
  - host: ops-agent.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: ops-agent
            port:
              number: 8000
```

#### 2. 部署到 Kubernetes

```bash
# 构建并推送镜像
docker build -t your-registry/ops-agent:latest .
docker push your-registry/ops-agent:latest

# 应用 Kubernetes 配置
kubectl apply -f k8s/deployment.yaml

# 查看部署状态
kubectl get pods -n ops-agent

# 查看日志
kubectl logs -f -n ops-agent deployment/ops-agent

# 初始化数据库（首次部署）
kubectl exec -it -n ops-agent deployment/ops-agent -- uv run python scripts/init_auth_db.py
```

---

## 🏗️ 系统架构

### DeepAgents 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                      用户层 (User Layer)                         │
│                  Web UI / 飞书 / API / Webhook                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              主智能体层 (Main Agent Layer)                        │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │         DeepAgents Main Agent (主智能体)                │    │
│  │                                                          │    │
│  │  🎯 核心能力:                                            │    │
│  │  • write_todos: 任务规划和分解                          │    │
│  │  • task(subagent, task): 委派任务给子智能体             │    │
│  │  • request_approval(action): 请求用户批准               │    │
│  │  • 智能路由: 根据意图和上下文决策工作流                 │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                中间件层 (Middleware Layer)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Approval    │  │  Security    │  │  Routing     │         │
│  │  Middleware  │  │  Middleware  │  │  Middleware  │         │
│  │  (批准流程)  │  │  (安全审核)  │  │  (智能路由)  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              子智能体层 (Subagents Layer)                         │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ intent-agent │  │  data-agent  │  │analyze-agent │         │
│  │  (意图识别)  │  │  (数据采集)  │  │  (分析决策)  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │execute-agent │  │ report-agent │  │ format-agent │         │
│  │  (执行操作)  │  │  (报告生成)  │  │  (响应格式化)│         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    工具层 (Tools Layer)                          │
│  K8s Tools / Prometheus Tools / Loki Tools / Command Executor   │
│  (所有工具支持 SDK 优先，自动降级到 CLI)                         │
└─────────────────────────────────────────────────────────────────┘
```

详细架构说明请查看 [DeepAgents 架构设计文档](./docs/DEEPAGENTS_ARCHITECTURE_DESIGN.md)。

---

## 📦 技术栈

### 后端

- **框架**: FastAPI 0.115+
- **AI 框架**: DeepAgents + LangGraph + LangChain
- **数据库**: SQLAlchemy 2.0 + SQLite
- **认证**: JWT + Passlib
- **LLM**: OpenAI / Claude / 智谱 AI / Ollama

### 前端

- **框架**: React 18 + TypeScript
- **UI 库**: Ant Design 5
- **状态管理**: React Query
- **构建工具**: Vite

### 集成

- **飞书**: lark-oapi SDK（长连接模式）
- **Kubernetes**: kubernetes Python SDK
- **Prometheus**: prometheus-api-client
- **Loki**: HTTP API

---

## 📚 文档

### 核心文档

- **[📖 项目完整文档](./PROJECT_DOCUMENTATION.md)** - 包含所有功能、架构、API、部署等详细说明
- **[📑 文档索引](./DOCUMENTATION_INDEX.md)** - 所有文档的分类索引
- **[🤖 Claude 指南](./CLAUDE.md)** - Claude Code 项目指南

### 功能文档

- **[🔧 工具降级机制](./docs/TOOL_FALLBACK_SUMMARY.md)** - SDK 优先，自动降级到命令行
- **[✅ 用户确认流程](./docs/APPROVAL_FLOW_IMPLEMENTATION_SUMMARY.md)** - 命令规划后暂停等待批准
- **[🔗 飞书集成](./docs/FEISHU_INTEGRATION.md)** - 飞书长连接和卡片交互
- **[💬 Web 聊天集成](./docs/WEB_CHAT_AGENT_INTEGRATION.md)** - Web UI 流式对话

### API 文档

- **[API 指南（中文）](./docs/api-guide-cn.md)**
- **[API 指南（英文）](./docs/api-guide.md)**

---

## 🔧 配置说明

### 环境变量配置

详细的环境变量说明请查看 [.env.example](./.env.example) 文件。

### 关键配置项

#### LLM 配置

```bash
# 选择 LLM 提供商
DEFAULT_LLM_PROVIDER=zhipu  # openai, claude, zhipu, ollama

# 智谱 AI 配置
ZHIPU_API_KEY=your_key_here
ZHIPU_MODEL=glm-4
```

#### 飞书配置

```bash
FEISHU_ENABLED=true
FEISHU_APP_ID=cli_xxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxx
FEISHU_CONNECTION_MODE=auto  # webhook | longconn | auto
```

#### Kubernetes 配置

```bash
K8S_ENABLED=true
KUBECONFIG=/path/to/kubeconfig
```

#### 安全配置

```bash
# JWT 密钥（生产环境必须修改）
JWT_SECRET_KEY=your-secret-key-here-change-in-production

# 安全环境
SECURITY_ENVIRONMENT=production  # production | testing | development
```

---

## 🛠️ 开发指南

### 项目结构

```
ops-agent-langgraph/
├── app/                         # 应用主目录
│   ├── main.py                  # FastAPI 应用入口
│   ├── deepagents/              # DeepAgents 主智能体和子智能体
│   ├── middleware/              # 中间件层
│   ├── tools/                   # Agent 工具集
│   ├── integrations/            # 外部服务集成
│   ├── api/                     # API 路由层
│   ├── core/                    # 核心模块
│   ├── models/                  # 数据库模型
│   ├── services/                # 业务服务层
│   └── schemas/                 # Pydantic 模式
├── frontend/                    # React 前端
├── config/                      # 配置文件
├── scripts/                     # 脚本工具
├── tests/                       # 测试套件
└── docs/                        # 文档
```

### 运行测试

```bash
# 所有测试
pytest tests/ -v

# 单元测试
pytest tests/unit/ -v

# 集成测试
pytest tests/integration/ -v

# 带覆盖率
pytest --cov=app --cov-report=html
```

### 代码质量

```bash
# 格式化代码
black app/ tests/

# 代码检查
ruff check app/ tests/

# 类型检查
mypy app/
```

---

## 🐛 故障排查

### 常见问题

#### 1. 数据库初始化失败

```bash
# 删除旧数据库
rm -rf data/ops_agent_v2.db

# 重新初始化
uv run python scripts/init_auth_db.py
```

#### 2. LLM API 调用失败

检查 `.env` 文件中的 API Key 配置：
```bash
# 验证 API Key
echo $ZHIPU_API_KEY
```

#### 3. 飞书长连接失败

检查飞书配置：
```bash
# 验证飞书配置
FEISHU_ENABLED=true
FEISHU_CONNECTION_MODE=longconn
```

#### 4. Docker 容器无法启动

查看容器日志：
```bash
docker-compose logs -f ops-agent
```

---

## 🤝 贡献

欢迎贡献代码、报告问题或提出建议！

### 贡献流程

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

---

## 📞 联系方式

- **维护者**: lanheader
- **项目地址**: https://github.com/your-org/ops-agent-langgraph
- **问题反馈**: https://github.com/your-org/ops-agent-langgraph/issues

---

## 🙏 致谢

感谢以下开源项目：

- [LangChain](https://github.com/langchain-ai/langchain)
- [LangGraph](https://github.com/langchain-ai/langgraph)
- [DeepAgents](https://github.com/langchain-ai/deepagents)
- [FastAPI](https://github.com/tiangolo/fastapi)
- [React](https://github.com/facebook/react)
- [Ant Design](https://github.com/ant-design/ant-design)

---

<div align="center">

**最后更新**: 2026-03-20

Made with ❤️ by Ops Team

</div>
