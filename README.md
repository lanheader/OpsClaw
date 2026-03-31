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

Ops Agent is an intelligent operations automation platform built on the **DeepAgents Framework**. It achieves full-process automation from monitoring, diagnosis to self-healing through the collaboration of a main agent and specialized sub-agents.

**Current Version**: v4.0 | **Subagents**: 6 | **Middleware**: 3 | **K8s Tools**: 28

### ✨ Key Features

#### 🤖 DeepAgents Architecture
- **Main Agent + 6 Specialized Subagents** working together
- **Intelligent Task Planning**: Automatic decomposition of complex tasks using `write_todos`
- **Subagent Delegation**: Delegate professional tasks via `task()` tool
- **Intelligent Routing**: Automatically decide workflow based on intent and context

#### 🛡️ Tools & Integrations
- **Tool Fallback Mechanism**: SDK first, auto fallback to CLI (kubectl/prometheus/loki)
- **28 K8s Tools**: 19 read + 3 write + 6 delete tools
- **Prometheus/Loki Integration**: Metrics query and log retrieval

#### 📨 Multi-Channel Messaging Architecture
- **Channel Abstraction Layer**: Unified message processing framework
- **Feishu Long Connection Mode**: Real-time message push with card interaction
- **Extensible Design**: Easily integrate new channels like Slack, DingTalk
- **AgentInvoker Enhancement**:
  - ⏰ Timeout Protection (300 seconds)
  - 🧠 Memory Injection (history + knowledge base)
  - 🔄 Self-Verification Retry (quality check + auto retry)
  - 💾 Fallback Reply (ensure friendly response)
  - 📚 Auto Learning (write to long-term memory)

#### 🔧 Middleware Layer (3 Middlewares)
- **ErrorFilteringMiddleware**: Filter tool call errors to prevent LLM from responding to errors
- **MessageTrimmingMiddleware**: Intelligently trim messages (keep last 40)
- **LoggingMiddleware**: Record model calls, tool execution, and latency

#### 🧠 Memory System (v3.5 SQLite FTS5)
- **Zero Dependencies**: No external embedding model required
- **FTS5 Full-Text Search**: BM25 ranking, unicode61 tokenizer for Chinese/English
- **LLM Query Expander**: Expands natural language to related keywords for better recall
- **LangGraph Store Integration**: Native memory access for DeepAgents
- **Smart Auto-Learning**: Filters out meaningless messages before storing

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+

### Clone & Install

```bash
git clone https://github.com/lanheader/OpsClaw.git
cd OpsClaw

# Install dependencies (UV recommended)
uv sync

# Or use pip
pip install -e .
```

### Configure

```bash
cp .env.example .env
vim .env
```

**Minimum Configuration**:
```bash
# LLM (required)
DEFAULT_LLM_PROVIDER=zhipu
ZHIPU_API_KEY=your_key_here

# Database (required)
DATABASE_URL=sqlite:///./data/ops_agent_v2.db
CHECKPOINT_DB_URL=sqlite:///./data/ops_checkpoints.db

# JWT Secret (required, change in production)
JWT_SECRET_KEY=your-secret-key-here-change-in-production
```

### Initialize & Start

```bash
mkdir -p data

# One-click initialization (recommended)
uv run python scripts/init.py

# Or skip knowledge base initialization
uv run python scripts/init.py --skip-kb

# Start server
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

> **Note**: `init.py` replaces multiple individual scripts. See [scripts/README.md](scripts/README.md) for details.

### Access

- **Web UI**: http://localhost:5173
- **API Docs**: http://localhost:8000/docs
- **Default Account**: `admin` / `admin123`

---

### Docker Deployment (Recommended for Production)

#### 1. Configure Environment

```bash
cp .env.example .env
vim .env  # Configure required variables
```

**Required Variables**:
```bash
# LLM (choose one)
DEFAULT_LLM_PROVIDER=openai  # or claude, zhipu, openrouter
OPENAI_API_KEY=your_key_here

# JWT Secret (change in production!)
JWT_SECRET_KEY=your-secret-key-change-in-production
```

#### 2. Build and Run

```bash
# Build image
docker-compose build

# Start service (auto-initializes on first run)
docker-compose up -d

# View logs
docker-compose logs -f ops-agent

# Stop service
docker-compose down
```

> **Note**: The container automatically initializes the database on first startup.

#### 3. Access

- **Web UI**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs (requires `ENABLE_DOCS=true`)
- **Default Account**: `admin` / `admin123`

#### 4. Production Deployment

```bash
# Use production configuration
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## 🏗️ System Architecture

### Architecture Diagram

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
│  │  • write_todos: Task planning and decomposition         │    │
│  │  • task(subagent, task): Delegate tasks to subagents    │    │
│  │  • request_approval(action): Request user approval      │    │
│  │  • Intelligent routing: Decide workflow by intent       │    │
│  │  • Tools: K8s(28) + Prometheus(3) + Loki(3) + More     │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              Middleware Layer (3 Middlewares)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Error       │  │  Message     │  │  Logging     │         │
│  │  Filtering   │  │  Trimming    │  │              │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              Subagents Layer (6 Subagents)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  data-agent  │  │analyze-agent │  │execute-agent │         │
│  │  (Data)      │  │  (Analysis)  │  │  (Execute)   │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │network-agent │  │security-agent│  │storage-agent │         │
│  │  (Network)   │  │  (Security)  │  │  (Storage)   │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              Memory System (SQLite FTS5)                         │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  SQLiteMemoryStore + SQLiteFTSStore                       │  │
│  │  • Zero dependencies (no embedding model)                 │  │
│  │  • FTS5 full-text search + BM25 ranking                   │  │
│  │  • LLM query expander for better recall                   │  │
│  │  • LangGraph BaseStore integration                        │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Tools Layer                                   │
│  K8s Tools (28) / Prometheus Tools (3) / Loki Tools (3)         │
│  Command Executor / Alert Tools / Chat History Tools            │
└─────────────────────────────────────────────────────────────────┘
```

### Checkpointer Architecture

```
┌─────────────────────────────────────────┐
│  LangGraph Checkpointer (独立数据库)      │
│  • 数据库: ops_checkpoints.db           │
│  • 后端: AsyncSqliteSaver               │
│  • thread_id = session_id              │
│  • 会话状态持久化，重启不丢失             │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  业务数据库 (独立)                       │
│  • 数据库: ops_agent_v2.db             │
│  • 表: chat_sessions, chat_messages    │
│  • RBAC: users, roles, permissions     │
│  • 审批: approval_config               │
└─────────────────────────────────────────┘
```

> **设计决策**: Checkpointer 和业务表使用独立的 SQLite 文件，避免并发写入锁竞争。

---

## 🧠 Memory System

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Application Layer                                  │
│                                                                             │
│   AgentInvoker.invoke_agent()                                               │
│       │                                                                     │
│       ├── 1️⃣ Memory Injection (build_context)                               │
│       │    └── Retrieve relevant memories → Enhance user query              │
│       │                                                                     │
│       ├── 2️⃣ Agent Execution (with store parameter)                         │
│       │    └── DeepAgents can access memory via store natively              │
│       │                                                                     │
│       └── 3️⃣ Auto-Learning (auto_learn_from_result)                         │
│            └── Incident resolved → Auto-store memory                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MemoryManager                                     │
│                         (Unified Memory Entry)                               │
│                                                                             │
│   Functions:                                                                 │
│   ├── remember_incident()     - Store incident memory                       │
│   ├── recall_similar_incidents() - Retrieve similar incidents               │
│   ├── learn_knowledge()       - Store knowledge                             │
│   ├── query_knowledge()       - Query knowledge                             │
│   ├── summarize_session()     - Generate session summary                    │
│   ├── build_context()         - Build context for prompt injection          │
│   └── auto_learn_from_result() - Auto-learn from results                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
┌───────────────────────────────┐   ┌───────────────────────────────┐
│     SQLiteMemoryStore         │   │     SQLiteFTSStore            │
│     (Business Layer)          │   │     (LangGraph Store Adapter)  │
│                               │   │                               │
│   Database: ./data/memory.db  │   │   Database: ./data/memory_fts.db│
│                               │   │                               │
│   Tables:                     │   │   Implements BaseStore:        │
│   ├── incidents_fts           │   │   ├── aput/aput               │
│   │   └── incidents_meta      │   │   ├── aget/aget               │
│   ├── knowledge_fts           │   │   ├── adelete/adelete         │
│   │   └── knowledge_meta      │   │   ├── asearch/asearch (FTS5)  │
│   └── session_summaries       │   │   └── abatch/abatch           │
│                               │   │                               │
└───────────────────────────────┘   └───────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           QueryExpander                                     │
│                         (Keyword Expansion)                                  │
│                                                                             │
│   Purpose: Bridge the semantic gap in keyword search                        │
│                                                                             │
│   Examples:                                                                  │
│   "pod crash" → "pod crash OOMKilled CrashLoopBackOff RestartCount"        │
│   "db connection failed" → "db connection timeout mysql max_connections"   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Memory Components

```
app/memory/
├── __init__.py               # Module exports, get_langgraph_store()
├── memory_manager.py         # Unified memory manager
├── sqlite_memory_store.py    # Business layer storage (incidents/knowledge/summary)
├── sqlite_fts_store.py       # LangGraph BaseStore adapter
└── query_expander.py         # LLM query expansion (with cache)
```

### Features

| Feature | Description |
|---------|-------------|
| **Zero Dependencies** | No embedding model required |
| **FTS5 Full-Text Search** | BM25 ranking, unicode61 tokenizer |
| **Chinese/English Support** | Built-in unicode61 tokenizer |
| **Query Expansion** | LLM expands keywords for better recall |
| **LangGraph Integration** | Native store parameter support |
| **Auto-Learning** | Smart filtering of meaningless messages |

### Auto-Learning

System automatically learns from operations conversations with smart filtering:
- ✅ **Learn**: Incident diagnosis, fix operations, knowledge Q&A (length ≥ 10 chars)
- ❌ **Skip**: "/new", "/help", "你好", "谢谢" and other meaningless messages

### Session Summary

Session summaries use overwrite strategy (fixed doc_id) to avoid storage bloat.

---

## 🤖 Subagents

| Subagent | File | Responsibility | Tools |
|----------|------|----------------|-------|
| **data-agent** | `subagents/data_agent.py` | Data collection | k8s_tools, prometheus_tools, loki_tools |
| **analyze-agent** | `subagents/analyze_agent.py` | Analysis & diagnosis | None (pure reasoning) |
| **execute-agent** | `subagents/execute_agent.py` | Execute operations | command_executor, k8s_tools |
| **network-agent** | `subagents/network_agent.py` | Network diagnosis | k8s_tools, network diagnostic tools |
| **security-agent** | `subagents/security_agent.py` | Security audit | k8s_tools |
| **storage-agent** | `subagents/storage_agent.py` | Storage troubleshooting | k8s_tools |

---

## 🔧 Middleware

| 中间件 | 文件 | 职责 |
|--------|------|------|
| **ErrorFilteringMiddleware** | `error_filtering_middleware.py` | 过滤工具错误消息，防止 LLM 响应错误 |
| **MessageTrimmingMiddleware** | `message_trimming_middleware.py` | 智能截断消息（保留最近 40 条，优先完整轮次） |
| **LoggingMiddleware** | `logging_middleware.py` | 记录 LLM 调用、工具执行、耗时 |

---

## 📦 Tech Stack

| 类别 | 技术 |
|------|------|
| **Framework** | FastAPI 0.115+ |
| **AI** | DeepAgents + LangGraph + LangChain |
| **Database** | SQLAlchemy 2.0 + SQLite (分离: 业务 + Checkpointer) |
| **Auth** | JWT + Passlib |
| **LLM** | OpenAI / Claude / Zhipu AI / Ollama |
| **Memory Store** | SQLite FTS5 (内置) |
| **Keyword Store** | SQLite FTS5 (内置) |
| **Logging** | Loguru |
| **Frontend** | React 18 + TypeScript + Ant Design 5 + Vite |
| **Feishu** | lark-oapi SDK (long connection) |
| **K8s** | kubernetes Python SDK |
| **Prometheus** | prometheus-api-client |
| **Loki** | HTTP API |

---

## 🔧 Configuration

### Key Config Items

```bash
# LLM
DEFAULT_LLM_PROVIDER=zhipu  # openai, claude, zhipu, ollama

# Database (separated storage)
DATABASE_URL=sqlite:///./data/ops_agent_v2.db
CHECKPOINT_DB_URL=sqlite:///./data/ops_checkpoints.db

# Memory System (SQLite FTS5, zero dependencies)
MEMORY_DB_PATH=./data/memory.db

# Feishu
FEISHU_ENABLED=true
FEISHU_LONG_CONNECTION_ENABLED=true

# Middleware
# MessageTrimming: MAX_MESSAGES_TO_KEEP=40, MIN_MESSAGES_TO_KEEP=10
```

---

## 📁 Project Structure

```
OpsClaw/
├── app/
│   ├── main.py                      # FastAPI 入口
│   ├── core/
│   │   ├── checkpointer.py          # LangGraph Checkpointer (独立 DB)
│   │   ├── config.py                # 配置管理
│   │   ├── state.py                 # OpsState 状态定义
│   │   ├── llm_factory.py           # LLM 工厂
│   │   └── permissions.py           # 权限系统
│   ├── deepagents/
│   │   ├── main_agent.py            # 主智能体 (单例 + Checkpointer)
│   │   ├── factory.py               # Agent 工厂
│   │   └── subagents/               # 子智能体 (6 个)
│   │       ├── data_agent.py        # 数据采集
│   │       ├── analyze_agent.py     # 分析决策
│   │       ├── execute_agent.py     # 执行操作
│   │       ├── network_agent.py     # 网络诊断
│   │       ├── security_agent.py    # 安全巡检
│   │       └── storage_agent.py     # 存储排查
│   ├── middleware/                   # 中间件 (3 个)
│   │   ├── error_filtering_middleware.py
│   │   ├── message_trimming_middleware.py
│   │   └── logging_middleware.py
│   ├── memory/                      # 记忆系统 (SQLite FTS5)
│   │   ├── memory_manager.py        # 统一管理器
│   │   ├── sqlite_memory_store.py   # 业务层存储
│   │   ├── sqlite_fts_store.py      # LangGraph BaseStore 适配
│   │   └── query_expander.py        # LLM 查询扩展
│   ├── tools/                       # 工具层 (SDK → CLI 降级)
│   │   ├── k8s/                     # K8s 工具 (19 read + 3 write + 6 delete)
│   │   ├── prometheus/              # Prometheus 工具
│   │   ├── loki/                    # Loki 工具
│   │   └── command_executor/        # 命令执行
│   ├── integrations/
│   │   ├── messaging/               # 多渠道消息架构
│   │   │   ├── base_channel.py
│   │   │   ├── message_processor.py
│   │   │   ├── adapters/
│   │   │   └── handlers/
│   │   │       ├── agent_invoker.py # Agent 调用 (含记忆注入)
│   │   │       └── approval_handler.py
│   │   ├── feishu/                  # 飞书集成
│   │   ├── kubernetes/              # K8s 集成
│   │   ├── prometheus/              # Prometheus 集成
│   │   └── loki/                    # Loki 集成
│   ├── models/                      # 数据库模型
│   ├── services/                    # 业务服务
│   ├── prompts/                     # 提示词管理
│   ├── api/v1/ & v2/               # API 路由
│   ├── schemas/                     # Pydantic schemas
│   └── utils/                       # 工具函数
├── frontend/                        # React 前端
├── config/                          # 配置文件
├── scripts/                         # 脚本工具
├── tests/                           # 测试
└── docs/                            # 文档
```

---

## 🤝 Contributing

1. Fork
2. Create branch (`git checkout -b feature/xxx`)
3. Commit (`git commit -m 'Add xxx'`)
4. Push (`git push origin feature/xxx`)
5. Open PR

---

## 📄 License

MIT License

---

<div align="center">

**Last Updated**: 2026-03-31 | **Version**: v4.0 | **Maintainer**: lanjiaxuan

</div>
