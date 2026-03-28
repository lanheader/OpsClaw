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

**Current Version**: v3.4 | **Subagents**: 3 | **Middleware**: 3 | **K8s Tools**: 28

### ✨ Key Features

#### 🤖 DeepAgents Architecture
- **Main Agent + 3 Specialized Subagents** working together
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

#### 🧠 Dual-Engine Memory System (v3.4 New)
- **Vector Mode (ChromaDB)**: Semantic search with cosine distance, requires embedding model
- **Keyword Mode (SQLite FTS5)**: Zero-dependency keyword search with BM25 ranking, no embedding needed
- **LLM Query Expander**: Expands natural language to related keywords for better recall
- **Auto Mode Switch**: Controlled by `ENABLE_VECTOR_MEMORY` config
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

# Memory (optional, default: vector mode)
ENABLE_VECTOR_MEMORY=true  # Set false for production without embedding model

# JWT Secret (required, change in production)
JWT_SECRET_KEY=your-secret-key-here-change-in-production
```

### Initialize & Start

```bash
mkdir -p data
uv run python scripts/init_auth_db.py
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Access

- **Web UI**: http://localhost:5173
- **API Docs**: http://localhost:8000/docs
- **Default Account**: `admin` / `admin123`

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
│              Subagents Layer (3 Subagents)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │intent-agent  │  │  data-agent  │  │analyze-agent │         │
│  │  (Intent)    │  │  (Data)      │  │  (Analysis)  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│  ┌──────────────┐                                              │
│  │execute-agent │                                              │
│  │  (Execute)   │                                              │
│  └──────────────┘                                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              Memory System (Dual Engine)                         │
│  ┌──────────────────────┐  ┌──────────────────────┐           │
│  │  ChromaDB (Vector)   │  │  SQLite FTS5 (Keyword)│          │
│  │  • Semantic search   │  │  • BM25 ranking      │          │
│  │  • Cosine distance   │  │  • Zero dependencies  │          │
│  │  • Needs embedding   │  │  • LLM query expand  │          │
│  └──────────────────────┘  └──────────────────────┘           │
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

### Dual-Engine Architecture

| 特性 | Vector Mode (ChromaDB) | Keyword Mode (SQLite FTS5) |
|------|----------------------|--------------------------|
| **依赖** | 需要 embedding 模型 | 零外部依赖 |
| **搜索方式** | 语义相似度 (cosine) | 关键词匹配 (BM25) |
| **适用场景** | 开发环境 (有 Ollama) | 生产环境 (无 embedding) |
| **配置** | `ENABLE_VECTOR_MEMORY=true` | `ENABLE_VECTOR_MEMORY=false` |
| **查询扩展** | 不需要 | LLM 自动扩展关键词 |

### Memory Components

```
app/memory/
├── memory_manager.py        # 统一记忆管理器 (双模式切换)
├── chroma_store.py          # ChromaDB 向量存储 (vector 模式)
├── sqlite_memory_store.py   # SQLite FTS5 存储 (keyword 模式)
├── query_expander.py        # LLM 查询扩展 (keyword 模式)
├── langgraph_store.py       # LangGraph BaseStore 适配器
└── vector_store.py          # 向量存储工具函数
```

### Auto-Learning

系统自动从运维对话中学习，但有智能过滤：
- ✅ **学习**: 故障诊断、修复操作、知识问答（长度 ≥ 10 字符）
- ❌ **跳过**: "/new"、"/help"、"你好"、"谢谢" 等无意义消息

### Session Summary

会话摘要采用覆盖更新策略（固定 doc_id），避免存储膨胀。

---

## 🤖 Subagents

| Subagent | 文件 | 职责 | 工具 |
|----------|------|------|------|
| **data-agent** | `subagents/data_agent.py` | 数据采集 | k8s_tools, prometheus_tools, loki_tools |
| **analyze-agent** | `subagents/analyze_agent.py` | 分析决策 | 无（纯推理） |
| **execute-agent** | `subagents/execute_agent.py` | 执行操作 | command_executor, k8s_tools |

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
| **Vector Store** | ChromaDB (可选) |
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

# Database (分离存储)
DATABASE_URL=sqlite:///./data/ops_agent_v2.db
CHECKPOINT_DB_URL=sqlite:///./data/ops_checkpoints.db

# Memory System
ENABLE_VECTOR_MEMORY=true  # true=ChromaDB, false=SQLite FTS5

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
│   │   └── subagents/               # 子智能体
│   │       ├── data_agent.py
│   │       ├── analyze_agent.py
│   │       └── execute_agent.py
│   ├── middleware/                   # 中间件 (3 个)
│   │   ├── error_filtering_middleware.py
│   │   ├── message_trimming_middleware.py
│   │   └── logging_middleware.py
│   ├── memory/                      # 记忆系统 (双引擎)
│   │   ├── memory_manager.py        # 统一管理器
│   │   ├── chroma_store.py          # ChromaDB 向量存储
│   │   ├── sqlite_memory_store.py   # SQLite FTS5 关键词存储
│   │   ├── query_expander.py        # LLM 查询扩展
│   │   ├── langgraph_store.py       # LangGraph BaseStore 适配
│   │   └── vector_store.py          # 向量工具
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

**Last Updated**: 2026-03-28 | **Version**: v3.4 | **Maintainer**: lanjiaxuan

</div>
