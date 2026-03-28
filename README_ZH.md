# Ops Agent (DeepAgents Edition)

<div align="center">

**智能运维自动化平台 - 基于 DeepAgents 框架**

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![DeepAgents](https://img.shields.io/badge/DeepAgents-latest-green)](https://github.com/langchain-ai/deepagents)
[![LangGraph](https://img.shields.io/badge/LangGraph-latest-green)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[English](README.md) | 简体中文

</div>

---

## 📖 项目简介

Ops Agent 是一个基于 **DeepAgents 框架**的智能运维自动化平台，通过主智能体和多个专业化子智能体协同工作，实现从监控、诊断到自愈的全流程自动化。

**当前版本**: v3.3 | **子智能体**: 6 个 | **中间件**: 5 个 | **K8s 工具**: 19 个

### ✨ 核心特性

#### 🤖 DeepAgents 架构
- **主智能体 + 6 个专业子智能体**协同工作
- **智能任务规划**：使用 `write_todos` 自动分解复杂任务
- **子智能体委派**：通过 `task()` 工具委派专业任务
- **智能路由**：根据意图和上下文自动决策工作流

#### 🛡️ 工具与集成
- **工具降级机制**：SDK 优先，自动降级到 CLI（kubectl/prometheus/loki）
- **19 个 K8s 读工具**：覆盖 Pod、Deployment、Service、ConfigMap 等
- **3 个 K8s 写工具**：重启、扩容、更新镜像
- **Prometheus/Loki 集成**：指标查询和日志检索

#### 📨 多渠道消息架构（v3.3 新增）
- **渠道抽象层**：统一的消息处理框架
- **飞书长连接模式**：实时消息推送，支持卡片交互
- **可扩展设计**：轻松接入 Slack、钉钉等新渠道
- **AgentInvoker 链路增强**：
  - ⏰ 超时保护（300 秒）
  - 🧠 记忆注入（历史对话和知识库）
  - 🔄 自我验证重试（质量检查 + 自动重试）
  - 💾 空回复兜底（确保用户收到友好提示）
  - 📚 自动学习（对话写入长期记忆）

#### 🔧 中间件层（5 个）
- **ErrorFilteringMiddleware**：过滤工具调用错误，防止 LLM 响应错误消息
- **ContextCompressionMiddleware**：压缩早期历史消息为摘要（≥30 条触发）
- **MessageTrimmingMiddleware**：智能截断消息（保留最近 40 条）
- **LoggingMiddleware**：记录模型调用、工具执行和耗时
- **MemoryEnhancedAgent**：从 SQLite FTS5 检索相关历史知识，增强上下文

#### 🧠 记忆系统（v3.5 SQLite FTS5）
- **零外部依赖**：无需 embedding 模型，可部署到任何服务器
- **FTS5 全文搜索**：BM25 排序，unicode61 分词器支持中英文
- **LLM 查询扩展**：自动扩展关键词，弥补语义搜索不足
- **LangGraph Store 集成**：DeepAgents 可原生访问记忆
- **智能自动学习**：过滤无意义消息，只存储有价值的知识

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
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

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

#### 1. 构建和启动

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

#### 2. 初始化数据库（首次启动）

```bash
# 进入容器
docker-compose exec ops-agent bash

# 初始化数据库
uv run python scripts/init_auth_db.py

# 退出容器
exit
```

#### 3. 访问应用

- **Web UI**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs（需要在 .env 中设置 `ENABLE_DOCS=true`）
- **默认账号**: `admin` / `admin123`

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
│  ┌────────────────────────────────────────────────────────┐    │
│  │         DeepAgents Main Agent (主智能体)                │    │
│  │  • write_todos: 任务规划和分解                          │    │
│  │  • task(subagent, task): 委派任务给子智能体             │    │
│  │  • request_approval(action): 请求用户批准               │    │
│  │  • 智能路由: 根据意图和上下文决策工作流                 │    │
│  │  • 37 个工具: K8s(22) + Prometheus(3) + Loki(3) + 其他  │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                中间件层 (Middleware Layer) - 5 个中间件           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Error       │  │  Context     │  │  Message     │         │
│  │  Filtering   │  │  Compression │  │  Trimming    │         │
│  │  (错误过滤)  │  │  (上下文压缩)│  │  (消息截断)  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│  ┌──────────────┐  ┌──────────────┐                            │
│  │  Logging     │  │  Memory      │                            │
│  │  (日志记录)  │  │  Enhanced    │                            │
│  └──────────────┘  └──────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              子智能体层 (Subagents Layer) - 6 个                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │intent-agent  │  │  data-agent  │  │analyze-agent │         │
│  │  (意图识别)  │  │  (数据采集)  │  │  (分析决策)  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │execute-agent │  │ report-agent │  │ format-agent │         │
│  │  (执行操作)  │  │  (报告生成)  │  │  (格式化)    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    工具层 (Tools Layer)                          │
│  K8s Tools (22) / Prometheus Tools (3) / Loki Tools (3)         │
│  Command Executor / Alert Tools / Chat History Tools            │
│  (所有工具支持 SDK 优先，自动降级到 CLI)                         │
└─────────────────────────────────────────────────────────────────┘
```

### 多渠道消息架构（v3.3）

```
飞书/Slack/钉钉 → ChannelAdapter → IncomingMessage
  ↓
MessageProcessor (统一消息处理编排器)
  1. UserBindingHandler: 验证用户绑定
  2. SessionHandler: 获取/创建会话
  3. CommandHandler: 处理特殊命令（/new, /end, /help）
  4. ApprovalHandler: 检查审批状态
  5. AgentInvoker: 调用 Agent 处理（增强版）
     ├── 超时保护（300 秒）
     ├── 记忆注入（历史对话 + 知识库）
     ├── 自我验证重试（质量检查 + 自动重试）
     ├── 空回复兜底（确保友好提示）
     └── 自动学习（写入长期记忆）
```

---

## 🤖 子智能体说明

### 1. intent-agent（意图识别子智能体）
**文件**：`app/deepagents/subagents/__init__.py`
**职责**：识别用户意图，分类为查询、诊断、执行等类型
**输出**：intent_type, confidence, suggested_workflow

### 2. data-agent（数据采集子智能体）
**文件**：`app/deepagents/subagents/data_agent.py`
**职责**：执行数据采集命令，调用 K8s/Prometheus/Loki 工具
**工具**：
- k8s_tools - K8s 资源查询（SDK → CLI 降级）
  - 19 个读工具：get_pods, get_pod, get_pod_logs, get_pod_events, get_deployments, get_services, get_nodes, get_namespaces, get_events, get_config_maps, get_secrets, get_ingress, get_daemon_sets, get_stateful_sets, get_p_vs, get_p_v_cs, get_resource_quotas 等
  - 3 个写工具：restart_deployment, scale_deployment, update_deployment_image
- prometheus_tools - 指标查询（SDK → CLI 降级）
- loki_tools - 日志查询（SDK → CLI 降级）

### 3. analyze-agent（分析决策子智能体）
**文件**：`app/deepagents/subagents/analyze_agent.py`
**职责**：分析采集的数据，诊断问题根因，规划修复方案
**输出**：
- `root_cause`: 根本原因
- `severity`: 严重程度
- `remediation_plan`: 修复方案

### 4. execute-agent（执行操作子智能体）
**文件**：`app/deepagents/subagents/execute_agent.py`
**职责**：执行修复命令，监控执行结果
**工具**：command_executor_tools, k8s_tools

### 5. report-agent（报告生成子智能体）
**职责**：生成结构化报告，包含诊断结果和建议

### 6. format-agent（格式化子智能体）
**职责**：格式化输出，适配不同渠道（飞书卡片、Web UI、纯文本）

---

## 🔧 中间件层

### 1. ErrorFilteringMiddleware（错误消息过滤中间件）
**文件**：`app/middleware/error_filtering_middleware.py`
**职责**：过滤工具调用失败的错误消息，防止 LLM 在下一轮对话中对错误做出响应
**错误标记**：
- `"Error:"`
- `"is not a valid tool"`
- `"Tool execution failed"`
- `"tool not found"`

### 2. ContextCompressionMiddleware（上下文压缩中间件）
**文件**：`app/middleware/context_compression_middleware.py`
**职责**：压缩早期历史消息为摘要，保留最近完整消息
**触发条件**：消息数 >= 30 条时触发
**策略**：
- 保留最近 20 条完整消息
- 对更早的消息生成压缩摘要
- 摘要包含：用户需求、关键结论

### 3. MessageTrimmingMiddleware（消息截断中间件）
**文件**：`app/middleware/message_trimming_middleware.py`
**职责**：智能截断消息，避免 token 数量暴增
**配置**：
- `MAX_MESSAGES_TO_KEEP = 40` - 保留最近 40 条消息
- `MIN_MESSAGES_TO_KEEP = 10` - 最少保留 10 条消息
**策略**：优先保留完整的对话轮次

### 4. LoggingMiddleware（日志中间件）
**文件**：`app/middleware/logging_middleware.py`
**职责**：记录模型调用、工具执行和耗时
**功能**：
- 记录 LLM 调用开始/结束
- 记录工具调用参数和结果
- 支持请求追踪（session_id, request_id）

### 5. MemoryEnhancedAgent（记忆增强中间件）
**文件**：`app/middleware/memory_middleware.py`
**职责**：为 Agent 注入长期记忆上下文，增强跨会话知识检索
**功能**：
- 从 SQLite FTS5 检索相关历史知识
- 将记忆上下文注入到系统提示词
- 支持自动学习（将新对话写入记忆）

---

## 🧠 记忆系统

### 架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           应用层调用入口                                     │
│                                                                             │
│   AgentInvoker.invoke_agent()                                               │
│       │                                                                     │
│       ├── 1️⃣ 记忆注入 (build_context)                                       │
│       │    └── 检索相关记忆 → 增强用户查询                                    │
│       │                                                                     │
│       ├── 2️⃣ Agent 执行 (带 store 参数)                                     │
│       │    └── DeepAgents 可通过 store 原生访问记忆                          │
│       │                                                                     │
│       └── 3️⃣ 自动学习 (auto_learn_from_result)                              │
│            └── 故障处理完成 → 自动存储记忆                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MemoryManager                                     │
│                         (统一记忆管理入口)                                    │
│                                                                             │
│   功能:                                                                      │
│   ├── remember_incident()     - 存储故障记忆                                 │
│   ├── recall_similar_incidents() - 检索相似故障                              │
│   ├── learn_knowledge()       - 存储知识                                     │
│   ├── query_knowledge()       - 检索知识                                     │
│   ├── summarize_session()     - 生成会话摘要                                 │
│   ├── build_context()         - 构建上下文 (注入到 prompt)                   │
│   └── auto_learn_from_result() - 自动学习                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
┌───────────────────────────────┐   ┌───────────────────────────────┐
│     SQLiteMemoryStore         │   │     SQLiteFTSStore            │
│     (业务层存储)               │   │     (LangGraph Store 适配器)   │
│                               │   │                               │
│   数据库: ./data/memory.db    │   │   数据库: ./data/memory_fts.db│
│                               │   │                               │
│   表结构:                      │   │   实现 LangGraph BaseStore:   │
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
│                         (查询关键词扩展)                                      │
│                                                                             │
│   功能: 弥补关键词搜索的语义不足                                              │
│                                                                             │
│   示例:                                                                      │
│   "pod crash" → "pod crash OOMKilled CrashLoopBackOff RestartCount"        │
│   "数据库连不上" → "数据库 连接 超时 connection timeout mysql max_connections"│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 文件说明

| 文件 | 职责 |
|------|------|
| `memory_manager.py` | 统一入口，协调记忆注入、检索、学习 |
| `sqlite_memory_store.py` | 业务层存储（故障/知识/摘要） |
| `sqlite_fts_store.py` | LangGraph BaseStore 适配器 |
| `query_expander.py` | LLM 查询关键词扩展（带缓存） |

### 数据流

```
用户消息 → AgentInvoker
              │
              ├── 记忆注入流程 ─────────────────────────────────┐
              │   │                                              │
              │   ├── 1. 获取 MemoryManager                      │
              │   ├── 2. 调用 build_context()                    │
              │   │    ├── QueryExpander 扩展关键词               │
              │   │    ├── FTS5 搜索故障记忆 (BM25)               │
              │   │    ├── FTS5 搜索知识库 (BM25)                 │
              │   │    └── 检索会话摘要                           │
              │   ├── 3. 拼接上下文到用户查询                     │
              │   └── 4. 返回 enhanced_text                      │
              │                                                  │
              ├── Agent 执行 (store 参数 → SQLiteFTSStore)       │
              │                                                  │
              └── 自动学习流程 ←──────────────────────────────────┘
                   │
                   ├── 1. 判断是否为故障处理
                   ├── 2. 提取解决方案/根因
                   └── 3. 存储到 FTS5 (自动去重)
```

### 核心特性

| 特性 | 说明 |
|------|------|
| **零外部依赖** | 无需 embedding 模型，可部署到任何服务器 |
| **FTS5 全文搜索** | BM25 排序，unicode61 分词器支持中英文 |
| **查询扩展** | LLM 自动扩展关键词，弥补语义搜索不足 |
| **LangGraph 集成** | 原生 store 参数支持，DeepAgents 可直接访问 |
| **智能自动学习** | 过滤无意义消息，只存储有价值的内容 |

### 自动学习

系统自动从运维对话中学习，但有智能过滤：
- ✅ **学习**: 故障诊断、修复操作、知识问答（长度 ≥ 10 字符）
- ❌ **跳过**: "/new"、"/help"、"你好"、"谢谢" 等无意义消息

### 会话摘要

会话摘要采用覆盖更新策略（固定 doc_id），避免存储膨胀。

---

## 📨 多渠道消息架构

### 架构概述

`app/integrations/messaging/` 是新的渠道抽象层，将飞书特定逻辑与通用业务逻辑解耦，支持多渠道接入。

```
app/integrations/messaging/
├── base_channel.py          # 抽象基类 + 数据结构
├── registry.py              # 渠道适配器注册表
├── message_processor.py     # 通用消息处理编排器
├── adapters/
│   └── feishu_adapter.py    # 飞书渠道适配器
└── handlers/
    ├── user_binding_handler.py   # 用户绑定验证
    ├── session_handler.py        # 会话管理
    ├── command_handler.py        # 特殊命令（/new, /end, /help）
    ├── approval_handler.py       # 审批流程
    └── agent_invoker.py          # Agent 调用（增强版）
```

### 消息处理流程

```
飞书消息 → FeishuChannelAdapter → IncomingMessage
  ↓
MessageProcessor.process_message()
  1. UserBindingHandler: 验证用户绑定
  2. SessionHandler: 获取/创建会话
  3. CommandHandler: 处理特殊命令
  4. ApprovalHandler: 检查审批状态
  5. AgentInvoker: 调用 Agent 处理
```

### 关键数据结构

```python
# 统一入站消息格式
IncomingMessage(
    channel_type="feishu",
    message_id="om_xxx",
    sender_id="ou_xxx",
    chat_id="oc_xxx",
    text="用户消息",
    raw_content={...}
)

# 渠道上下文（贯穿整个处理流程）
ChannelContext(
    channel_type="feishu",
    chat_id="oc_xxx",
    session_id="feishu_abc123",
    user_id=1,
    user_permissions={"k8s:read", "k8s:write"},
    message_id="om_xxx"  # 用于添加表情回复
)
```

### API 端点

| 端点 | 说明 |
|------|------|
| `POST /api/v2/messaging/webhook/{channel_type}` | 统一 Webhook 入口 |
| `GET /api/v1/feishu/status` | 飞书集成状态查询 |
| `POST /api/v1/feishu/callback` | 飞书旧端点（兼容层，重定向到新架构） |

### 添加新渠道

```python
# 1. 实现适配器
class SlackChannelAdapter(BaseChannelAdapter):
    channel_type = "slack"
    async def verify_request(self, headers, body) -> bool: ...
    async def send_message(self, message: OutgoingMessage) -> Dict: ...

# 2. 注册（在 registry.py 的 initialize_channels() 中）
ChannelRegistry.register(SlackChannelAdapter(config))

# 3. 访问端点
# POST /api/v2/messaging/webhook/slack
```

---

## 📦 技术栈

### 后端

- **框架**: FastAPI 0.115+
- **AI 框架**: DeepAgents + LangGraph + LangChain
- **数据库**: SQLAlchemy 2.0 + SQLite
- **认证**: JWT + Passlib
- **LLM**: OpenAI / Claude / 智谱 AI / Ollama
- **记忆存储**: SQLite FTS5（零外部依赖，支持中英文全文搜索）
- **日志**: Loguru（自动异常捕获、日志轮转）

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
- **[🤖 Claude 指南](CLAUDE_bak.md)** - Claude Code 项目指南
- **[🔧 工具降级机制](./docs/TOOL_FALLBACK_SUMMARY.md)** - SDK 优先，自动降级到命令行
- **[🔗 飞书集成](./docs/FEISHU_INTEGRATION.md)** - 飞书长连接和卡片交互

---

## 🔧 配置说明

### 关键配置项

#### LLM 配置

```bash
DEFAULT_LLM_PROVIDER=zhipu  # openai, claude, zhipu, ollama
ZHIPU_API_KEY=your_key_here
ZHIPU_MODEL=glm-4
```

#### 飞书配置

```bash
FEISHU_ENABLED=true
FEISHU_APP_ID=cli_xxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxx
FEISHU_LONG_CONNECTION_ENABLED=true  # 启用长连接模式
```

#### 中间件配置

```bash
# 消息截断配置
MAX_MESSAGES_TO_KEEP=40  # 保留最近 40 条消息
MIN_MESSAGES_TO_KEEP=10  # 最少保留 10 条消息

# 上下文压缩配置
COMPRESSION_THRESHOLD=30  # 超过 30 条消息触发压缩
MAX_FULL_MESSAGES=20      # 保留最近 20 条完整消息
```

#### AgentInvoker 配置

```bash
# 超时配置
AGENT_TIMEOUT=300  # 5 分钟超时

# 重试配置
MAX_RETRY=1  # 最多重试 1 次
```

---

## 🛠️ 开发指南

### 项目结构

```
ops-agent-langgraph/
├── app/                         # 应用主目录
│   ├── main.py                  # FastAPI 应用入口
│   ├── deepagents/              # DeepAgents 主智能体和子智能体
│   │   ├── main_agent.py        # 主智能体
│   │   ├── factory.py           # Agent 工厂（FinalReportEnrichedAgent）
│   │   └── subagents/           # 子智能体
│   │       ├── data_agent.py    # 数据采集
│   │       ├── analyze_agent.py # 分析决策
│   │       └── execute_agent.py # 执行操作
│   ├── middleware/              # 中间件层
│   │   ├── error_filtering_middleware.py  # 错误消息过滤
│   │   ├── context_compression_middleware.py  # 上下文压缩
│   │   ├── message_trimming_middleware.py     # 消息截断
│   │   ├── logging_middleware.py              # 日志记录
│   │   └── memory_middleware.py               # 记忆增强
│   ├── tools/                   # Agent 工具集
│   │   ├── k8s/
│   │   │   ├── read_tools.py    # K8s 读工具（19 个）
│   │   │   ├── write_tools.py   # K8s 写工具（3 个）
│   │   │   └── delete_tools.py  # K8s 删除工具
│   │   ├── prometheus/
│   │   │   └── read_tools.py    # Prometheus 查询工具
│   │   ├── loki/
│   │   │   └── read_tools.py    # Loki 日志查询工具
│   │   └── command_executor/
│   │       └── read_tools.py    # 命令执行工具
│   ├── integrations/            # 外部服务集成
│   │   ├── messaging/           # 多渠道消息架构（v3.3）
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
│   │   │       └── agent_invoker.py  # 增强版
│   │   ├── feishu/              # 飞书集成
│   │   ├── kubernetes/          # K8s 集成
│   │   ├── prometheus/          # Prometheus 集成
│   │   └── loki/                # Loki 集成
│   ├── api/                     # API 路由层
│   │   ├── v1/                  # API v1
│   │   └── v2/                  # API v2
│   ├── core/                    # 核心模块
│   ├── models/                  # 数据库模型
│   ├── services/                # 业务服务层
│   ├── memory/                  # 记忆系统 (SQLite FTS5)
│   │   ├── memory_manager.py    # 统一管理器
│   │   ├── sqlite_memory_store.py # 业务层存储
│   │   └── sqlite_fts_store.py  # LangGraph BaseStore 适配
│   └── utils/                   # 工具函数
│       └── loguru_config.py     # Loguru 日志配置
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

---

## 🐛 故障排查

### 常见问题

#### 1. 服务重启后历史消息重复发送

**原因**：消息索引未持久化
**解决**：确保数据库中 `chat_sessions.last_processed_message_index` 字段存在

```bash
# 检查字段是否存在
sqlite3 data/ops_agent_v2.db "PRAGMA table_info(chat_sessions);" | grep last_processed
```

#### 2. 模型回答与当前问题不相关

**原因**：历史消息过多，上下文丢失
**解决**：检查中间件是否正常工作

```bash
# 查看日志中的压缩记录
grep "上下文压缩" logs/app.log
```

#### 3. AI 响应工具错误消息

**原因**：工具调用错误消息污染对话上下文
**解决**：ErrorFilteringMiddleware 自动过滤错误消息

```bash
# 检查中间件是否加载
grep "ErrorFilteringMiddleware" logs/app.log
```

#### 4. 用户收不到任何回复

**原因**：所有 AI 消息被过滤
**解决**：AgentInvoker 空回复兜底机制确保至少有一条友好回复

```bash
# 检查兜底回复日志
grep "所有尝试均未产生有效回复" logs/app.log
```

#### 5. HTTP 访问日志不显示

**原因**：uvicorn.access 日志级别设置为 WARNING
**解决**：修改 `app/utils/loguru_config.py` 中的日志级别为 INFO

```python
LOGGING_LEVELS = {
    "uvicorn.access": "INFO",  # 改为 INFO
}
```

#### 6. 数据库初始化失败

```bash
# 删除旧数据库
rm -rf data/ops_agent_v2.db

# 重新初始化
uv run python scripts/init_auth_db.py
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

- **维护者**: lanjiaxuan
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
- [SQLite FTS5](https://www.sqlite.org/fts5.html)
- [Loguru](https://github.com/Delgan/loguru)

---

<div align="center">

**最后更新**: 2026-03-27 | **版本**: v3.3

Made with ❤️ by Ops Team

</div>
