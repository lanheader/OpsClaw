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

**当前版本**: v3.2.1 | **子智能体**: 3 个 | **中间件**: 4 个

### ✨ 核心特性

- 🤖 **DeepAgents 架构**: 主智能体 + 3 个专业子智能体协同工作
- 🎯 **智能任务规划**: 使用 `write_todos` 自动分解复杂任务
- 🔄 **子智能体委派**: 通过 `task()` 工具委派专业任务
- 🛡️ **工具降级机制**: SDK 优先，自动降级到命令行工具
- 📉 **上下文压缩**: 自动压缩早期历史消息，保留关键信息
- 🔒 **错误消息过滤**: 过滤工具调用错误，防止 LLM 响应错误消息
- 💾 **后备回复机制**: 确保至少有一条友好回复发送给用户
- 📊 **多渠道接入**: 支持 Web UI 和飞书集成
- 🧠 **会话记忆**: 支持多轮对话和上下文记忆
- 🔒 **消息索引持久化**: 解决服务重启后重复发送历史消息问题
- 📡 **增强诊断**: 工作流执行期间实时收集诊断信息

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
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                中间件层 (Middleware Layer) - 4 个中间件           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Error       │  │  Context     │  │  Message     │         │
│  │  Filtering   │  │  Compression │  │  Trimming    │         │
│  │  (错误过滤)  │  │  (上下文压缩)│  │  (消息截断)  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│  ┌──────────────┐                                              │
│  │  Logging     │                                              │
│  │  (日志记录)  │                                              │
│  └──────────────┘                                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              子智能体层 (Subagents Layer) - 3 个                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  data-agent  │  │analyze-agent │  │execute-agent │         │
│  │  (数据采集)  │  │  (分析决策)  │  │  (执行操作)  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    工具层 (Tools Layer)                          │
│  K8s Tools / Prometheus Tools / Loki Tools / Command Executor   │
│  (所有工具支持 SDK 优先，自动降级到 CLI)                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🤖 子智能体说明

### 1. data-agent（数据采集子智能体）
**职责**：执行数据采集命令，调用 K8s/Prometheus/Loki 工具
**工具**：k8s_tools, prometheus_tools, loki_tools

### 2. analyze-agent（分析决策子智能体）
**职责**：分析采集的数据，诊断问题根因，规划修复方案
**输出**：root_cause, severity, remediation_plan

### 3. execute-agent（执行操作子智能体）
**职责**：执行修复命令，监控执行结果
**工具**：command_executor_tools, k8s_tools

---

## 🔧 中间件层

### 1. ErrorFilteringMiddleware（错误消息过滤中间件）
**文件**：`app/middleware/error_filtering_middleware.py`
**职责**：过滤工具调用错误消息，防止 LLM 响应错误消息
**错误标记**：`"Error:"`, `"is not a valid tool"`, `"Tool execution failed"`

### 2. ContextCompressionMiddleware（上下文压缩中间件）
**文件**：`app/middleware/context_compression_middleware.py`
**职责**：压缩早期历史消息为摘要，保留最近完整消息
**触发条件**：消息数 >= 30 条时触发

### 3. MessageTrimmingMiddleware（消息截断中间件）
**文件**：`app/middleware/message_trimming_middleware.py`
**职责**：智能截断消息，避免 token 数量暴增
**配置**：
- `MAX_MESSAGES_TO_KEEP = 40` - 保留最近 40 条消息
- `MIN_MESSAGES_TO_KEEP = 10` - 最少保留 10 条消息

### 4. LoggingMiddleware（日志中间件）
**文件**：`app/middleware/logging_middleware.py`
**职责**：记录模型调用、工具执行和耗时

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
- **[🤖 Claude 指南](./CLAUDE.md)** - Claude Code 项目指南
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
FEISHU_CONNECTION_MODE=auto  # webhook | longconn | auto
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

---

## 🛠️ 开发指南

### 项目结构

```
ops-agent-langgraph/
├── app/                         # 应用主目录
│   ├── main.py                  # FastAPI 应用入口
│   ├── deepagents/              # DeepAgents 主智能体和子智能体
│   │   ├── main_agent.py        # 主智能体
│   │   └── subagents/           # 子智能体
│   │       ├── data_agent.py    # 数据采集
│   │       ├── analyze_agent.py # 分析决策
│   │       └── execute_agent.py # 执行操作
│   ├── middleware/              # 中间件层
│   │   ├── error_filtering_middleware.py  # 错误消息过滤
│   │   ├── context_compression_middleware.py  # 上下文压缩
│   │   ├── message_trimming_middleware.py     # 消息截断
│   │   └── logging_middleware.py              # 日志记录
│   ├── tools/                   # Agent 工具集
│   │   └── k8s/
│   │       └── read_tools.py    # K8s 读工具（包含 get_config_maps）
│   ├── integrations/            # 外部服务集成
│   ├── api/                     # API 路由层
│   ├── core/                    # 核心模块
│   ├── models/                  # 数据库模型
│   └── services/                # 业务服务层
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

**原因**：所有 AI 消息被 should_skip_message 过滤
**解决**：后备回复机制确保至少有一条友好回复

```bash
# 检查后备回复日志
grep "后备回复" logs/app.log
```

#### 5. 数据库初始化失败

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

---

<div align="center">

**最后更新**: 2026-03-25 | **版本**: v3.2.1

Made with ❤️ by Ops Team

</div>
