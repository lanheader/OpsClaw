# Ops Agent (DeepAgents Edition)

<div align="center">

**Intelligent Operations Automation Platform - Powered by DeepAgents Framework**

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![DeepAgents](https://img.shields.io/badge/DeepAgents-latest-green)](https://github.com/langchain-ai/deepagents)
[![LangGraph](https://img.shields.io/badge/LangGraph-latest-green)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

English | [简体中文](README.md)

</div>

---

## 📖 Project Overview

**Current Version**: v3.0.0 | **Tools**: 24 tools across 6 groups | **Subagents**: 6 specialized agents

Ops Agent is an intelligent operations automation platform built on the **DeepAgents Framework**. It achieves full-process automation from monitoring, diagnosis to self-healing through the collaboration of a main agent and multiple specialized sub-agents.

### ✨ Key Features

- 🤖 **DeepAgents Architecture**: Main agent + 6 specialized sub-agents working together
- 🎯 **Intelligent Task Planning**: Automatic decomposition of complex tasks using `write_todos`
- 🔄 **Sub-agent Delegation**: Delegate professional tasks via `task()` tool
- 🛡️ **Tool Fallback Mechanism**: SDK first, automatically fallback to CLI tools (24 tools, 6 groups)
- 🔒 **Dynamic Permissions**: Tool permissions auto-discovered, 11 fine-grained permissions
- 🔐 **Middleware Architecture**: Approval process, security audit, intelligent routing
- 📊 **Multi-channel Access**: Support for Web UI and Feishu integration
- 🧠 **Session Memory**: Support for multi-turn conversations and context memory
- 🔐 **Access Control**: RBAC permission management and user authentication

### 🎯 Three Core Scenarios

1. **Interactive Cluster Status Query** 🔍 - Query K8s cluster real-time status via natural language
2. **Scheduled Inspection Reports** 📅 - Automatically execute cluster inspections on schedule and generate health reports
3. **Alert Automatic Diagnosis and Handling** 🚨 - Receive monitoring alerts, automatically diagnose and provide remediation plans

---

## 🚀 Quick Start

### Method 1: Local Development Environment

#### 1. Prerequisites

- Python 3.11+
- Node.js 18+
- UV (Python package manager)

#### 2. Clone Project

```bash
git clone https://github.com/your-org/ops-agent-langgraph.git
cd ops-agent-langgraph
```

#### 3. Install Dependencies

```bash
# Install Python dependencies using UV (recommended)
uv sync

# Or use pip
pip install -e .
```

#### 4. Configure Environment Variables

```bash
# Copy environment variable example
cp .env.example .env

# Edit .env to configure necessary parameters
vim .env
```

**Minimum Configuration**:
```bash
# LLM Configuration (required)
DEFAULT_LLM_PROVIDER=zhipu
ZHIPU_API_KEY=your_key_here

# Database (required)
DATABASE_URL=sqlite:///./data/ops_agent_v2.db

# JWT Secret (required, change in production)
JWT_SECRET_KEY=your-secret-key-here-change-in-production
```

#### 5. Initialize Database

```bash
# Create data directory
mkdir -p data

# Initialize database (includes RBAC tables and initial admin account)
uv run python scripts/init_auth_db.py
```

#### 6. Start Services

```bash
# Start backend service
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Start frontend service (new terminal)
cd frontend
npm install
npm run dev
```

#### 7. Access Application

- **Web UI**: http://localhost:5173
- **API Docs**: http://localhost:8000/docs
- **Default Account**: `admin` / `admin123`

---

### Method 2: Docker Deployment (Recommended for Production)

#### 1. Create Dockerfile

Create `Dockerfile` in project root:

```dockerfile
# Multi-stage build - Frontend build stage
FROM node:18-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy frontend dependency files
COPY frontend/package*.json ./

# Install frontend dependencies
RUN npm ci

# Copy frontend source
COPY frontend/ ./

# Build frontend
RUN npm run build

# Multi-stage build - Backend runtime stage
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install UV
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# Copy project files
COPY pyproject.toml uv.lock ./
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY config/ ./config/
COPY .env.example ./.env

# Install Python dependencies
RUN uv sync --frozen

# Copy frontend build artifacts
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start command
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### 2. Create docker-compose.yml

Create `docker-compose.yml` in project root:

```yaml
# Note: version field is optional in modern docker-compose
version: '3.8'

services:
  ops-agent:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: ops-agent
    ports:
      - "8000:8000"
    environment:
      # LLM Configuration
      - DEFAULT_LLM_PROVIDER=${DEFAULT_LLM_PROVIDER:-zhipu}
      - ZHIPU_API_KEY=${ZHIPU_API_KEY}
      - ZHIPU_MODEL=${ZHIPU_MODEL:-glm-4}

      # Database
      - DATABASE_URL=sqlite:///./data/ops_agent_v2.db

      # JWT
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}

      # Feishu Configuration (optional)
      - FEISHU_ENABLED=${FEISHU_ENABLED:-false}
      - FEISHU_APP_ID=${FEISHU_APP_ID}
      - FEISHU_APP_SECRET=${FEISHU_APP_SECRET}

      # K8s Configuration (optional)
      - K8S_ENABLED=${K8S_ENABLED:-false}
      - KUBECONFIG=/app/.kube/config

      # Prometheus Configuration (optional)
      - PROMETHEUS_ENABLED=${PROMETHEUS_ENABLED:-false}
      - PROMETHEUS_URL=${PROMETHEUS_URL}

      # Loki Configuration (optional)
      - LOKI_ENABLED=${LOKI_ENABLED:-false}
      - LOKI_URL=${LOKI_URL}

      # Security Configuration
      - SECURITY_ENVIRONMENT=${SECURITY_ENVIRONMENT:-production}

      # API Configuration
      - ENABLE_DOCS=${ENABLE_DOCS:-false}
      - ENABLE_CORS=${ENABLE_CORS:-true}
      - CORS_ORIGINS=${CORS_ORIGINS:-http://localhost:5173}

    volumes:
      # Persistent data
      - ./data:/app/data
      # K8s configuration (if needed)
      - ~/.kube:/app/.kube:ro
      # Security policy configuration
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

#### 3. Create .dockerignore

Create `.dockerignore` in project root:

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

# Tests and coverage
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

# Environment variables
.env
.env.local
.env.*.local

# Database
*.db
*.sqlite
*.sqlite3
data/

# Logs
*.log
logs/

# Frontend
frontend/node_modules/
frontend/dist/
frontend/.next/
frontend/out/

# Git
.git/
.gitignore

# Documentation
docs/
*.md
!README.md

# Others
.DS_Store
*.bak
*.tmp
```

#### 4. Build and Start

```bash
# Build image
docker-compose build

# Start service
docker-compose up -d

# View logs
docker-compose logs -f

# Stop service
docker-compose down
```

#### 5. Initialize Database (First Start)

```bash
# Enter container
docker-compose exec ops-agent bash

# Initialize database
uv run python scripts/init_auth_db.py

# Exit container
exit
```

#### 6. Access Application

- **Web UI**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs (set `ENABLE_DOCS=true` in .env)
- **Default Account**: `admin` / `admin123`

---

### Method 3: Kubernetes Deployment

#### 1. Create Kubernetes Deployment File

Create `k8s/deployment.yaml`:

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

#### 2. Deploy to Kubernetes

```bash
# Build and push image
docker build -t your-registry/ops-agent:latest .
docker push your-registry/ops-agent:latest

# Apply Kubernetes configuration
kubectl apply -f k8s/deployment.yaml

# View deployment status
kubectl get pods -n ops-agent

# View logs
kubectl logs -f -n ops-agent deployment/ops-agent

# Initialize database (first deployment)
kubectl exec -it -n ops-agent deployment/ops-agent -- uv run python scripts/init_auth_db.py
```

---

## 🏗️ System Architecture

### DeepAgents Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      User Layer                                 │
│                  Web UI / Feishu / API / Webhook                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              Main Agent Layer                                    │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │         DeepAgents Main Agent                            │    │
│  │                                                          │    │
│  │  🎯 Core Capabilities:                                  │    │
│  │  • write_todos: Task planning and decomposition          │    │
│  │  • task(subagent, task): Delegate tasks to sub-agents   │    │
│  │  • request_approval(action): Request user approval       │    │
│  │  • Intelligent routing: Decide workflow based on intent │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                Middleware Layer                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Approval    │  │  Security    │  │  Routing     │         │
│  │  Middleware  │  │  Middleware  │  │  Middleware  │         │
│  │  (Approval)  │  │  (Security)  │  │  (Routing)   │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              Subagents Layer                                     │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ intent-agent │  │  data-agent  │  │analyze-agent │         │
│  │  (Intent)    │  │  (Data)      │  │  (Analysis)  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │execute-agent │  │ report-agent │  │ format-agent │         │
│  │  (Execute)   │  │  (Report)    │  │  (Format)    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Tools Layer                                   │
│  K8s Tools / Prometheus Tools / Loki Tools / Command Executor   │
│  (All tools support SDK first, auto fallback to CLI)            │
└─────────────────────────────────────────────────────────────────┘
```

For detailed architecture documentation, see [DeepAgents Architecture Design](./docs/DEEPAGENTS_ARCHITECTURE_DESIGN.md).

---

## 📦 Tech Stack

### Backend

- **Framework**: FastAPI 0.115+
- **AI Framework**: DeepAgents + LangGraph + LangChain
- **Database**: SQLAlchemy 2.0 + SQLite
- **Authentication**: JWT + Passlib
- **LLM**: OpenAI / Claude / Zhipu AI / Ollama

### Frontend

- **Framework**: React 18 + TypeScript
- **UI Library**: Ant Design 5
- **State Management**: React Query
- **Build Tool**: Vite

### Integrations

- **Feishu**: lark-oapi SDK (long connection mode)
- **Kubernetes**: kubernetes Python SDK
- **Prometheus**: prometheus-api-client
- **Loki**: HTTP API

---

## 📚 Documentation

### Core Documentation

- **[📖 Complete Project Documentation](./PROJECT_DOCUMENTATION.md)** - Complete details on all features, architecture, API, deployment, etc.
- **[📑 Documentation Index](./DOCUMENTATION_INDEX.md)** - Categorized index of all documentation
- **[🤖 Claude Guide](./CLAUDE.md)** - Claude Code project guide

### Feature Documentation

- **[🔧 Tool Fallback Mechanism](./docs/TOOL_FALLBACK_SUMMARY.md)** - SDK first, auto fallback to command line
- **[✅ User Approval Flow](./docs/APPROVAL_FLOW_IMPLEMENTATION_SUMMARY.md)** - Pause after command planning waiting for approval
- **[🔗 Feishu Integration](./docs/FEISHU_INTEGRATION.md)** - Feishu long connection and card interaction
- **[💬 Web Chat Integration](./docs/WEB_CHAT_AGENT_INTEGRATION.md)** - Web UI streaming conversation

### API Documentation

- **[API Guide (English)](./docs/api-guide.md)**
- **[API 指南（中文）](./docs/api-guide-cn.md)**

---

## 🔧 Configuration

### Environment Variables

For detailed environment variable documentation, see [.env.example](./.env.example).

### Key Configuration Items

#### LLM Configuration

```bash
# Select LLM provider
DEFAULT_LLM_PROVIDER=zhipu  # openai, claude, zhipu, ollama

# Zhipu AI configuration
ZHIPU_API_KEY=your_key_here
ZHIPU_MODEL=glm-4
```

#### Feishu Configuration

```bash
FEISHU_ENABLED=true
FEISHU_APP_ID=cli_xxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxx
FEISHU_CONNECTION_MODE=auto  # webhook | longconn | auto
```

#### Kubernetes Configuration

```bash
K8S_ENABLED=true
KUBECONFIG=/path/to/kubeconfig
```

#### Security Configuration

```bash
# JWT Secret (must change in production)
JWT_SECRET_KEY=your-secret-key-here-change-in-production

# Security Environment
SECURITY_ENVIRONMENT=production  # production | testing | development
```

---

## 🛠️ Development Guide

### Project Structure

```
ops-agent-langgraph/
├── app/                         # Application main directory
│   ├── main.py                  # FastAPI application entry
│   ├── deepagents/              # DeepAgents main agent and sub-agents
│   ├── middleware/              # Middleware layer
│   ├── tools/                   # Agent tools
│   ├── integrations/            # External service integrations
│   ├── api/                     # API route layer
│   ├── core/                    # Core modules
│   ├── models/                  # Database models
│   ├── services/                # Business service layer
│   └── schemas/                 # Pydantic schemas
├── frontend/                    # React frontend
├── config/                      # Configuration files
├── scripts/                     # Script tools
├── tests/                       # Test suite
└── docs/                        # Documentation
```

### Running Tests

```bash
# All tests
pytest tests/ -v

# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# With coverage
pytest --cov=app --cov-report=html
```

### Code Quality

```bash
# Format code
black app/ tests/

# Check code
ruff check app/ tests/

# Type check
mypy app/
```

---

## 🐛 Troubleshooting

### Common Issues

#### 1. Database Initialization Failed

```bash
# Remove old database
rm -rf data/ops_agent_v2.db

# Re-initialize
uv run python scripts/init_auth_db.py
```

#### 2. LLM API Call Failed

Check API Key configuration in `.env`:
```bash
# Verify API Key
echo $ZHIPU_API_KEY
```

#### 3. Feishu Long Connection Failed

Check Feishu configuration:
```bash
# Verify Feishu configuration
FEISHU_ENABLED=true
FEISHU_CONNECTION_MODE=longconn
```

#### 4. Docker Container Failed to Start

View container logs:
```bash
docker-compose logs -f ops-agent
```

---

## 🤝 Contributing

Contributions are welcome! Feel free to submit issues, fork the repository, and create pull requests.

### Contribution Flow

1. Fork this repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

---

## 📄 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) file for details.

---

## 📞 Contact

- **Maintainer**: lanheader
- **Project URL**: https://github.com/your-org/ops-agent-langgraph
- **Issue Tracker**: https://github.com/your-org/ops-agent-langgraph/issues

---

## 🙏 Acknowledgments

Thanks to the following open source projects:

- [LangChain](https://github.com/langchain-ai/langchain)
- [LangGraph](https://github.com/langchain-ai/langgraph)
- [DeepAgents](https://github.com/langchain-ai/deepagents)
- [FastAPI](https://github.com/tiangolo/fastapi)
- [React](https://github.com/facebook/react)
- [Ant Design](https://github.com/ant-design/ant-design)

---

<div align="center">

**Last Updated**: 2026-03-22 | **Version**: v3.0.0

Made with ❤️ by Ops Team

</div>
