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

**Current Version**: v3.3 | **Subagents**: 6 | **Middleware**: 5 | **K8s Tools**: 19

### ✨ Key Features

#### 🤖 DeepAgents Architecture
- **Main Agent + 6 Specialized Subagents** working together
- **Intelligent Task Planning**: Automatic decomposition of complex tasks using `write_todos`
- **Subagent Delegation**: Delegate professional tasks via `task()` tool
- **Intelligent Routing**: Automatically decide workflow based on intent and context

#### 🛡️ Tools & Integrations
- **Tool Fallback Mechanism**: SDK first, auto fallback to CLI (kubectl/prometheus/loki)
- **19 K8s Read Tools**: Covering Pod, Deployment, Service, ConfigMap, etc.
- **3 K8s Write Tools**: Restart, scale, update image
- **Prometheus/Loki Integration**: Metrics query and log retrieval

#### 📨 Multi-Channel Messaging Architecture (v3.3 New)
- **Channel Abstraction Layer**: Unified message processing framework
- **Feishu Long Connection Mode**: Real-time message push with card interaction
- **Extensible Design**: Easily integrate new channels like Slack, DingTalk
- **AgentInvoker Enhancement**:
  - ⏰ Timeout Protection (300 seconds)
  - 🧠 Memory Injection (history + knowledge base)
  - 🔄 Self-Verification Retry (quality check + auto retry)
  - 💾 Fallback Reply (ensure friendly response)
  - 📚 Auto Learning (write to long-term memory)

#### 🔧 Middleware Layer (5 Middlewares)
- **ErrorFilteringMiddleware**: Filter tool call errors to prevent LLM from responding to errors
- **ContextCompressionMiddleware**: Compress early history messages into summaries (≥30 messages)
- **MessageTrimmingMiddleware**: Intelligently trim messages (keep last 40)
- **LoggingMiddleware**: Record model calls, tool execution, and latency
- **MemoryEnhancedAgent**: Retrieve relevant historical knowledge from ChromaDB

#### 🧠 Memory System
- **ChromaDB Vector Store**: Lightweight, easy-to-use, pure Python implementation
- **Cross-Session Long-Term Memory**: Automatic learning and knowledge accumulation
- **Message Index Persistence**: Solves duplicate historical messages after service restart

### 🎯 Three Core Scenarios

1. **Interactive Cluster Status Query** 🔍 - Query K8s cluster real-time status via natural language
2. **Scheduled Inspection Reports** 📅 - Automatically execute cluster inspections and generate health reports
3. **Alert Automatic Diagnosis and Handling** 🚨 - Receive monitoring alerts, diagnose and provide remediation plans

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

# Stop service
docker-compose down
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
│  │  • write_todos: Task planning and decomposition         │    │
│  │  • task(subagent, task): Delegate tasks to subagents    │    │
│  │  • request_approval(action): Request user approval      │    │
│  │  • Intelligent routing: Decide workflow by intent       │    │
│  │  • 37 tools: K8s(22) + Prometheus(3) + Loki(3) + More   │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                Middleware Layer (5 Middlewares)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Error       │  │  Context     │  │  Message     │         │
│  │  Filtering   │  │  Compression │  │  Trimming    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│  ┌──────────────┐  ┌──────────────┐                            │
│  │  Logging     │  │  Memory      │                            │
│  │              │  │  Enhanced    │                            │
│  └──────────────┘  └──────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              Subagents Layer (6 Subagents)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │intent-agent  │  │  data-agent  │  │analyze-agent │         │
│  │  (Intent)    │  │  (Data)      │  │  (Analysis)  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │execute-agent │  │ report-agent │  │ format-agent │         │
│  │  (Execute)   │  │  (Report)    │  │  (Format)    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Tools Layer                                   │
│  K8s Tools (22) / Prometheus Tools (3) / Loki Tools (3)         │
│  Command Executor / Alert Tools / Chat History Tools            │
│  (All tools support SDK first, auto fallback to CLI)            │
└─────────────────────────────────────────────────────────────────┘
```

### Multi-Channel Messaging Architecture (v3.3)

```
Feishu/Slack/DingTalk → ChannelAdapter → IncomingMessage
  ↓
MessageProcessor (Unified Message Processing Orchestrator)
  1. UserBindingHandler: Verify user binding
  2. SessionHandler: Get/create session
  3. CommandHandler: Handle special commands (/new, /end, /help)
  4. ApprovalHandler: Check approval status
  5. AgentInvoker: Invoke Agent (Enhanced)
     ├── Timeout Protection (300s)
     ├── Memory Injection (history + knowledge base)
     ├── Self-Verification Retry (quality check + auto retry)
     ├── Fallback Reply (ensure friendly response)
     └── Auto Learning (write to long-term memory)
```

---

## 🤖 Subagents Description

### 1. intent-agent (Intent Recognition Subagent)
**File**: `app/deepagents/subagents/__init__.py`
**Responsibility**: Recognize user intent, classify as query, diagnosis, execution, etc.
**Output**: intent_type, confidence, suggested_workflow

### 2. data-agent (Data Collection Subagent)
**File**: `app/deepagents/subagents/data_agent.py`
**Responsibility**: Execute data collection commands, call K8s/Prometheus/Loki tools
**Tools**:
- k8s_tools - K8s resource query (SDK → CLI fallback)
  - 19 read tools: get_pods, get_pod, get_pod_logs, get_pod_events, get_deployments, get_services, get_nodes, get_namespaces, get_events, get_config_maps, get_secrets, get_ingress, get_daemon_sets, get_stateful_sets, get_p_vs, get_p_v_cs, get_resource_quotas, etc.
  - 3 write tools: restart_deployment, scale_deployment, update_deployment_image
- prometheus_tools - Metrics query (SDK → CLI fallback)
- loki_tools - Log query (SDK → CLI fallback)

### 3. analyze-agent (Analysis Subagent)
**File**: `app/deepagents/subagents/analyze_agent.py`
**Responsibility**: Analyze collected data, diagnose root cause, plan remediation
**Output**:
- `root_cause`: Root cause
- `severity`: Severity level
- `remediation_plan`: Remediation plan

### 4. execute-agent (Execution Subagent)
**File**: `app/deepagents/subagents/execute_agent.py`
**Responsibility**: Execute remediation commands, monitor execution results
**Tools**: command_executor_tools, k8s_tools

### 5. report-agent (Report Generation Subagent)
**Responsibility**: Generate structured reports with diagnosis results and recommendations

### 6. format-agent (Formatting Subagent)
**Responsibility**: Format output for different channels (Feishu cards, Web UI, plain text)

---

## 🔧 Middleware Layer

### 1. ErrorFilteringMiddleware (Error Message Filtering)
**File**: `app/middleware/error_filtering_middleware.py`
**Responsibility**: Filter tool call errors to prevent LLM from responding to errors
**Error Markers**:
- `"Error:"`
- `"is not a valid tool"`
- `"Tool execution failed"`
- `"tool not found"`

### 2. ContextCompressionMiddleware (Context Compression)
**File**: `app/middleware/context_compression_middleware.py`
**Responsibility**: Compress early history messages into summaries, preserve recent full messages
**Trigger**: Activated when message count >= 30
**Strategy**:
- Keep last 20 full messages
- Compress earlier messages into summaries
- Summary includes: user requirements, key conclusions

### 3. MessageTrimmingMiddleware (Message Trimming)
**File**: `app/middleware/message_trimming_middleware.py`
**Responsibility**: Intelligently trim messages to avoid token explosion
**Config**:
- `MAX_MESSAGES_TO_KEEP = 40` - Keep last 40 messages
- `MIN_MESSAGES_TO_KEEP = 10` - Minimum 10 messages
**Strategy**: Prioritize keeping complete conversation turns

### 4. LoggingMiddleware (Logging)
**File**: `app/middleware/logging_middleware.py`
**Responsibility**: Record model calls, tool execution, and latency
**Features**:
- Record LLM call start/end
- Record tool call parameters and results
- Support request tracing (session_id, request_id)

### 5. MemoryEnhancedAgent (Memory Enhancement)
**File**: `app/middleware/memory_middleware.py`
**Responsibility**: Inject long-term memory context for Agent, enhance cross-session knowledge retrieval
**Features**:
- Retrieve relevant historical knowledge from vector store (ChromaDB)
- Inject memory context into system prompt
- Support auto learning (write new conversations to memory)

---

## 📨 Multi-Channel Messaging Architecture

### Architecture Overview

`app/integrations/messaging/` is the new channel abstraction layer that decouples Feishu-specific logic from general business logic, supporting multi-channel access.

```
app/integrations/messaging/
├── base_channel.py          # Abstract base class + data structures
├── registry.py              # Channel adapter registry
├── message_processor.py     # Unified message processing orchestrator
├── adapters/
│   └── feishu_adapter.py    # Feishu channel adapter
└── handlers/
    ├── user_binding_handler.py   # User binding verification
    ├── session_handler.py        # Session management
    ├── command_handler.py        # Special commands (/new, /end, /help)
    ├── approval_handler.py       # Approval process
    └── agent_invoker.py          # Agent invocation (Enhanced)
```

### Message Processing Flow

```
Feishu Message → FeishuChannelAdapter → IncomingMessage
  ↓
MessageProcessor.process_message()
  1. UserBindingHandler: Verify user binding
  2. SessionHandler: Get/create session
  3. CommandHandler: Handle special commands
  4. ApprovalHandler: Check approval status
  5. AgentInvoker: Invoke Agent
```

### Key Data Structures

```python
# Unified incoming message format
IncomingMessage(
    channel_type="feishu",
    message_id="om_xxx",
    sender_id="ou_xxx",
    chat_id="oc_xxx",
    text="User message",
    raw_content={...}
)

# Channel context (throughout the processing flow)
ChannelContext(
    channel_type="feishu",
    chat_id="oc_xxx",
    session_id="feishu_abc123",
    user_id=1,
    user_permissions={"k8s:read", "k8s:write"},
    message_id="om_xxx"  # For adding emoji reactions
)
```

### API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/v2/messaging/webhook/{channel_type}` | Unified Webhook entry |
| `GET /api/v1/feishu/status` | Feishu integration status query |
| `POST /api/v1/feishu/callback` | Feishu legacy endpoint (compatibility layer) |

### Adding New Channels

```python
# 1. Implement adapter
class SlackChannelAdapter(BaseChannelAdapter):
    channel_type = "slack"
    async def verify_request(self, headers, body) -> bool: ...
    async def send_message(self, message: OutgoingMessage) -> Dict: ...

# 2. Register (in registry.py's initialize_channels())
ChannelRegistry.register(SlackChannelAdapter(config))

# 3. Access endpoint
# POST /api/v2/messaging/webhook/slack
```

---

## 📦 Tech Stack

### Backend

- **Framework**: FastAPI 0.115+
- **AI Framework**: DeepAgents + LangGraph + LangChain
- **Database**: SQLAlchemy 2.0 + SQLite
- **Authentication**: JWT + Passlib
- **LLM**: OpenAI / Claude / Zhipu AI / Ollama
- **Vector Store**: ChromaDB (lightweight, pure Python)
- **Logging**: Loguru (auto exception capture, log rotation)

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
- **[🔧 Tool Fallback Mechanism](./docs/TOOL_FALLBACK_SUMMARY.md)** - SDK first, auto fallback to CLI
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
FEISHU_LONG_CONNECTION_ENABLED=true  # Enable long connection mode
```

#### Middleware Configuration

```bash
# Message trimming configuration
MAX_MESSAGES_TO_KEEP=40  # Keep last 40 messages
MIN_MESSAGES_TO_KEEP=10  # Minimum 10 messages

# Context compression configuration
COMPRESSION_THRESHOLD=30  # Trigger compression when > 30 messages
MAX_FULL_MESSAGES=20      # Keep last 20 full messages
```

#### AgentInvoker Configuration

```bash
# Timeout configuration
AGENT_TIMEOUT=300  # 5 minutes timeout

# Retry configuration
MAX_RETRY=1  # Maximum 1 retry
```

---

## 🛠️ Development Guide

### Project Structure

```
ops-agent-langgraph/
├── app/                         # Application main directory
│   ├── main.py                  # FastAPI application entry
│   ├── deepagents/              # DeepAgents main agent and subagents
│   │   ├── main_agent.py        # Main agent
│   │   ├── factory.py           # Agent factory (FinalReportEnrichedAgent)
│   │   └── subagents/           # Subagents
│   │       ├── data_agent.py    # Data collection
│   │       ├── analyze_agent.py # Analysis
│   │       └── execute_agent.py # Execution
│   ├── middleware/              # Middleware layer
│   │   ├── error_filtering_middleware.py  # Error filtering
│   │   ├── context_compression_middleware.py  # Context compression
│   │   ├── message_trimming_middleware.py     # Message trimming
│   │   ├── logging_middleware.py              # Logging
│   │   └── memory_middleware.py               # Memory enhancement
│   ├── tools/                   # Agent tools
│   │   ├── k8s/
│   │   │   ├── read_tools.py    # K8s read tools (19)
│   │   │   ├── write_tools.py   # K8s write tools (3)
│   │   │   └── delete_tools.py  # K8s delete tools
│   │   ├── prometheus/
│   │   │   └── read_tools.py    # Prometheus query tools
│   │   ├── loki/
│   │   │   └── read_tools.py    # Loki log query tools
│   │   └── command_executor/
│   │       └── read_tools.py    # Command execution tools
│   ├── integrations/            # External service integrations
│   │   ├── messaging/           # Multi-channel messaging (v3.3)
│   │   │   ├── base_channel.py
│   │   │   ├── registry.py
│   │   │   ├── message_processor.py
│   │   │   ├── adapters/
│   │   │   │   └── feishu_adapter.py
│   │   │   └── handlers/
│   │   │       ├── user_binding_handler.py
│   │   │       ├── session_handler.py
│   │   │       ├── command_handler.py
│   │   │       ├── approval_handler.py
│   │   │       └── agent_invoker.py  # Enhanced
│   │   ├── feishu/              # Feishu integration
│   │   ├── kubernetes/          # K8s integration
│   │   ├── prometheus/          # Prometheus integration
│   │   └── loki/                # Loki integration
│   ├── api/                     # API route layer
│   │   ├── v1/                  # API v1
│   │   └── v2/                  # API v2
│   ├── core/                    # Core modules
│   ├── models/                  # Database models
│   ├── services/                # Business service layer
│   ├── memory/                  # Memory system
│   │   ├── chroma_store.py      # ChromaDB vector store
│   │   └── memory_manager.py    # Memory manager
│   └── utils/                   # Utility functions
│       └── loguru_config.py     # Loguru logging config
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

#### 2. Model Response Irrelevant to Current Question

**Cause**: Too many historical messages, context lost
**Solution**: Check if middleware is working properly

```bash
# View compression records in logs
grep "上下文压缩" logs/app.log
```

#### 3. AI Responds to Tool Error Messages

**Cause**: Tool call errors polluting conversation context
**Solution**: ErrorFilteringMiddleware automatically filters error messages

```bash
# Check if middleware is loaded
grep "ErrorFilteringMiddleware" logs/app.log
```

#### 4. No Reply Sent to User

**Cause**: All AI messages filtered
**Solution**: AgentInvoker fallback reply mechanism ensures at least one friendly response

```bash
# Check fallback reply logs
grep "所有尝试均未产生有效回复" logs/app.log
```

#### 5. HTTP Access Logs Not Showing

**Cause**: uvicorn.access log level set to WARNING
**Solution**: Modify log level to INFO in `app/utils/loguru_config.py`

```python
LOGGING_LEVELS = {
    "uvicorn.access": "INFO",  # Change to INFO
}
```

#### 6. Database Initialization Failed

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
- [ChromaDB](https://github.com/chroma-core/chroma)
- [Loguru](https://github.com/Delgan/loguru)

---

<div align="center">

**Last Updated**: 2026-03-27 | **Version**: v3.3

Made with ❤️ by Ops Team

</div>
