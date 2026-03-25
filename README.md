# Ops Agent (DeepAgents Edition)

<div align="center">

**Intelligent Operations Automation Platform - Powered by DeepAgents Framework**

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![DeepAgents](https://img.shields.io/badge/DeepAgents-latest-green)](https://github.com/langchain-ai/deepagents)
[![LangGraph](https://img.shields.io/badge/LangGraph-latest-green)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

English | [简体中文](README_ZH.md)

</div>

---

## 📖 Project Overview

**Current Version**: v3.2.0 | **Subagents**: 3 | **Middleware**: 3

Ops Agent is an intelligent operations automation platform built on the **DeepAgents Framework**. It achieves full-process automation from monitoring, diagnosis to self-healing through the collaboration of a main agent and specialized sub-agents.

### ✨ Key Features

- 🤖 **DeepAgents Architecture**: Main agent + 3 specialized sub-agents working together
- 🎯 **Intelligent Task Planning**: Automatic decomposition of complex tasks using `write_todos`
- 🔄 **Sub-agent Delegation**: Delegate professional tasks via `task()` tool
- 🛡️ **Tool Fallback Mechanism**: SDK first, automatically fallback to CLI tools
- 📉 **Context Compression**: Automatically compress early history messages, preserve key information
- 📊 **Multi-channel Access**: Support for Web UI and Feishu integration
- 🧠 **Session Memory**: Support for multi-turn conversations and context memory
- 🔒 **Message Index Persistence**: Solves the issue of duplicate historical messages after service restart

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
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

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

#### 1. Build and Start

```bash
# Build image
docker-compose build

# Start service
docker-compose up -d

# View logs
docker-compose logs -f
```

#### 2. Initialize Database (First Start)

```bash
# Enter container
docker-compose exec ops-agent bash

# Initialize database
uv run python scripts/init_auth_db.py

# Exit container
exit
```

#### 3. Access Application

- **Web UI**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs (set `ENABLE_DOCS=true` in .env)
- **Default Account**: `admin` / `admin123`

---

## 🏗️ System Architecture

### DeepAgents Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      User Layer                                  │
│                  Web UI / Feishu / API / Webhook                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              Main Agent Layer                                    │
│  ┌────────────────────────────────────────────────────────┐    │
│  │         DeepAgents Main Agent                           │    │
│  │  🎯 Core Capabilities:                                  │    │
│  │  • write_todos: Task planning and decomposition         │    │
│  │  • task(subagent, task): Delegate tasks to sub-agents   │    │
│  │  • request_approval(action): Request user approval      │    │
│  │  • Intelligent routing: Decide workflow based on intent │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                Middleware Layer                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Context     │  │  Message     │  │  Logging     │         │
│  │  Compression │  │  Trimming    │  │  Middleware  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              Subagents Layer - 3 Agents                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  data-agent  │  │analyze-agent │  │execute-agent │         │
│  │  (Data)      │  │  (Analysis)  │  │  (Execute)   │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Tools Layer                                   │
│  K8s Tools / Prometheus Tools / Loki Tools / Command Executor   │
│  (All tools support SDK first, auto fallback to CLI)            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🤖 Subagents Description

### 1. data-agent (Data Collection Subagent)
**File**: `app/deepagents/subagents/data_agent.py`
**Responsibility**: Execute data collection commands, call K8s/Prometheus/Loki tools
**Tools**: k8s_tools, prometheus_tools, loki_tools

### 2. analyze-agent (Analysis Subagent)
**File**: `app/deepagents/subagents/analyze_agent.py`
**Responsibility**: Analyze collected data, diagnose root cause, plan remediation
**Output**: root_cause, severity, remediation_plan

### 3. execute-agent (Execution Subagent)
**File**: `app/deepagents/subagents/execute_agent.py`
**Responsibility**: Execute remediation commands, monitor execution results
**Tools**: command_executor_tools, k8s_tools

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

- **[📖 Complete Project Documentation](./PROJECT_DOCUMENTATION.md)** - Complete details on all features, architecture, API, deployment
- **[🤖 Claude Guide](./CLAUDE.md)** - Claude Code project guide
- **[🔧 Tool Fallback Mechanism](./docs/TOOL_FALLBACK_SUMMARY.md)** - SDK first, auto fallback to command line
- **[🔗 Feishu Integration](./docs/FEISHU_INTEGRATION.md)** - Feishu long connection and card interaction

---

## 🔧 Configuration

### Key Configuration Items

#### LLM Configuration

```bash
DEFAULT_LLM_PROVIDER=zhipu  # openai, claude, zhipu, ollama
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

#### Middleware Configuration

```bash
# Message trimming configuration
MAX_MESSAGES_TO_KEEP=40
MIN_MESSAGES_TO_KEEP=10

# Context compression configuration
COMPRESSION_THRESHOLD=30
MAX_FULL_MESSAGES=20
```

---

## 🛠️ Development Guide

### Project Structure

```
ops-agent-langgraph/
├── app/                         # Application main directory
│   ├── main.py                  # FastAPI application entry
│   ├── deepagents/              # DeepAgents main agent and sub-agents
│   │   ├── main_agent.py        # Main agent
│   │   └── subagents/           # Sub-agents
│   │       ├── data_agent.py    # Data collection
│   │       ├── analyze_agent.py # Analysis
│   │       └── execute_agent.py # Execution
│   ├── middleware/              # Middleware layer
│   │   ├── context_compression_middleware.py
│   │   ├── message_trimming_middleware.py
│   │   └── logging_middleware.py
│   ├── tools/                   # Agent tools
│   ├── integrations/            # External service integrations
│   ├── api/                     # API route layer
│   ├── core/                    # Core modules
│   ├── models/                  # Database models
│   └── services/                # Business service layer
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

---

## 🐛 Troubleshooting

### Common Issues

#### 1. Historical Messages Re-sent After Service Restart

**Cause**: Message index not persisted
**Solution**: Ensure `chat_sessions.last_processed_message_index` column exists in database

```bash
# Check if column exists
sqlite3 data/ops_agent_v2.db "PRAGMA table_info(chat_sessions);" | grep last_processed
```

#### 2. Model Answers Unrelated to Current Question

**Cause**: Too many historical messages, context lost
**Solution**: Check if middleware is working properly

```bash
# View compression logs
grep "上下文压缩" logs/app.log
```

#### 3. Database Initialization Failed

```bash
# Remove old database
rm -rf data/ops_agent_v2.db

# Re-initialize
uv run python scripts/init_auth_db.py
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

- **Maintainer**: lanjiaxuan
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

**Last Updated**: 2026-03-25 | **Version**: v3.2.0

Made with ❤️ by Ops Team

</div>
