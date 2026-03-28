# CLAUDE.md - Ops Agent

> Claude Code 项目指南，帮助 AI 助手理解项目架构和开发约束

---

**注意**：团队成员使用的模型是 "claude-4.6-opus"，不要修改这个字符串。

## 🎯 项目定位

**Ops Agent 是一个智能运维自动化平台，不是通用的 AI 聊天机器人。**

核心场景：
- 🔍 交互式集群状态查询
- 📅 定时巡检报告
- 🚨 告警自动诊断与处理

---

## 🏗️ 架构分层（严格遵守！）

```
┌─────────────────────────────────────────┐
│  主智能体 (DeepAgents Main Agent)       │
│  - 规划: write_todos                    │
│  - 委派: task(subagent, task)           │
│  - 批准: request_approval(action)       │
│  - 路由: 智能决策                       │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│  中间件层 (Middleware) - 3 个中间件     │
│  - ErrorFilteringMiddleware: 错误过滤   │
│  - MessageTrimmingMiddleware: 消息截断  │
│  - LoggingMiddleware: 日志记录          │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│  子智能体层 (Subagents) - 3 个         │
│  - data-agent: 数据采集                 │
│  - analyze-agent: 分析决策              │
│  - execute-agent: 执行操作              │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│  工具层 (Tools with @tool)              │
│  - k8s_tools (SDK → CLI 降级)           │
│  - prometheus_tools (SDK → CLI 降级)    │
│  - loki_tools (SDK → CLI 降级)          │
│  - command_executor_tools               │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│  记忆系统 (Dual Engine)                 │
│  - ChromaDB (vector, 需 embedding)      │
│  - SQLite FTS5 (keyword, 零依赖)       │
└─────────────────────────────────────────┘
```

### ⚠️ 分层约束

| 层级 | ✅ 允许 | ❌ 禁止 |
|------|---------|---------|
| **主智能体** | 规划、委派、路由 | 直接调工具、操作数据库 |
| **中间件** | 拦截、增强、过滤 | 修改业务逻辑 |
| **子智能体** | 推理、选择工具、调用工具 | 直接 kubectl、跳过工具层 |
| **工具层** | 具体实现、SDK/CLI 降级 | 关心业务逻辑 |

---

## 📁 代码分层映射

| 层级 | 代码位置 | 可调用的层 |
|------|---------|-----------|
| **主智能体** | `app/deepagents/main_agent.py` | → 子智能体 |
| **中间件** | `app/middleware/` | → 拦截增强 |
| **子智能体** | `app/deepagents/subagents/` | → 工具层 |
| **工具层** | `app/tools/` | → `app/integrations/` |
| **记忆系统** | `app/memory/` | → 独立存储 |
| **API 层** | `app/api/` | → 主智能体 |
| **消息处理** | `app/integrations/messaging/` | → 主智能体 |

---

## 🧠 记忆系统（v3.4 双引擎）

### 架构

```
MemoryManager (统一入口)
├── ENABLE_VECTOR_MEMORY=true  → ChromaStore (语义搜索)
│   ├── cosine 距离
│   ├── 需要 embedding 模型
│   └── 直接用 user_query 搜索
│
└── ENABLE_VECTOR_MEMORY=false → SQLiteMemoryStore (关键词搜索)
    ├── FTS5 + BM25 排序
    ├── 零外部依赖
    ├── QueryExpander: LLM 扩展关键词
    └── 生产环境推荐
```

### 文件说明

| 文件 | 职责 |
|------|------|
| `memory_manager.py` | 统一入口，双模式切换，自动学习 |
| `chroma_store.py` | ChromaDB 向量存储（cosine 距离） |
| `sqlite_memory_store.py` | SQLite FTS5 关键词存储（BM25） |
| `query_expander.py` | LLM 查询扩展（带缓存） |
| `langgraph_store.py` | LangGraph BaseStore 适配器 |

### 关键设计

1. **记忆注入统一到 AgentInvoker**：`agent_invoker.py` 是唯一注入点
2. **自动学习有过滤**：长度 < 10 或无意义消息（你好、谢谢等）不学习
3. **会话摘要覆盖更新**：固定 doc_id，避免膨胀
4. **ChromaDB 集合统一 embedding_function**：创建和查询用同一个 embedding 模型

---

## 💾 Checkpointer 设计

```
业务数据库: ops_agent_v2.db
  ├── chat_sessions / chat_messages
  ├── users / roles / permissions
  └── approval_config

Checkpointer 数据库: ops_checkpoints.db  ← 独立！
  ├── checkpoints
  └── checkpoint_writes
```

- **thread_id = session_id**，通过 `get_thread_config(session_id)` 生成
- **所有会话共享同一个编译图**，通过 thread_id 区分状态
- **shutdown 时关闭连接**：`shutdown_checkpointer()` 在 FastAPI shutdown 事件中调用

---

## 🤖 子智能体

### 1. data-agent（数据采集）
- **文件**: `app/deepagents/subagents/data_agent.py`
- **工具**: k8s_tools (28个), prometheus_tools (3个), loki_tools (3个)
- **委派**: `task("data-agent", "采集集群数据")`

### 2. analyze-agent（分析决策）
- **文件**: `app/deepagents/subagents/analyze_agent.py`
- **工具**: 无（纯推理）
- **输出**: root_cause, severity, remediation_plan
- **委派**: `task("analyze-agent", "分析数据并诊断问题")`

### 3. execute-agent（执行操作）
- **文件**: `app/deepagents/subagents/execute_agent.py`
- **工具**: command_executor_tools, k8s_tools
- **委派**: `task("execute-agent", "执行修复操作")`

---

## 🔧 中间件

| 中间件 | 职责 |
|--------|------|
| **ErrorFilteringMiddleware** | 过滤工具错误（"Error:", "Tool execution failed" 等） |
| **MessageTrimmingMiddleware** | 保留最近 40 条消息，优先完整轮次 |
| **LoggingMiddleware** | 记录 LLM 调用、工具执行、耗时 |

> **注意**: ContextCompressionMiddleware 已删除（与 DeepAgents 内置 SummarizationMiddleware 冲突）。

---

## 🛠️ 工具降级机制

**所有工具必须支持 SDK 优先，CLI 降级！**

```python
async def execute(self, namespace: str = "default"):
    try:
        # 1. SDK
        result = self.k8s_client.core_v1.list_namespaced_pod(namespace)
        return tool_success_response(data, source="kubernetes-sdk")
    except Exception:
        # 2. CLI fallback
        result = await execute_command(f"kubectl get pods -n {namespace} -o json")
        return tool_success_response(result, source="kubectl")
```

---

## 📨 消息处理流程

```
飞书消息 → FeishuChannelAdapter → IncomingMessage
  ↓
MessageProcessor.process_message()
  1. UserBindingHandler: 用户绑定验证
  2. SessionHandler: 会话管理
  3. CommandHandler: 特殊命令 (/new, /end, /help)
  4. ApprovalHandler: 审批状态检查
  5. AgentInvoker: 调用 Agent
     ├── 记忆注入 (build_context → enhanced_text)
     ├── Agent 调用 (astream + checkpointer)
     ├── 质量检查 + 自动重试
     ├── 后备回复
     └── 自动学习 (auto_learn_from_result)
```

---

## 🔐 批准流程

DeepAgents 使用 `interrupt_on` 机制实现：

```python
# main_agent.py
interrupt_on = {"restart_deployment": True, "delete_pod": True}
agent = create_deep_agent(..., interrupt_on=interrupt_on)
```

审批配置从数据库动态加载（`ApprovalConfigService`），支持按角色配置。

---

## 🚫 常见错误

### ❌ 主智能体直接操作工具
```python
# 错误
result = await k8s_tools.get_pods(namespace)

# 正确
result = await task("data-agent", "采集集群数据")
```

### ❌ 子智能体跳过工具层
```python
# 错误
result = os.popen(f"kubectl get pods -n {namespace}")

# 正确
return await self.k8s_tools.get_pods(namespace)
```

---

## 🧪 测试策略

```bash
# 工具层
pytest tests/unit/tools/ -v

# 子智能体
pytest tests/unit/deepagents/ -v

# 中间件
pytest tests/unit/middleware/ -v

# 集成测试
pytest tests/integration/ -v
```

---

## 📚 参考资料

- [DeepAgents Overview](https://docs.langchain.com/oss/python/deepagents/overview)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LangGraph Checkpointer](https://langchain-ai.github.io/langgraph/concepts/persistence/)

---

**最后更新**: 2026-03-28 | **版本**: v3.4 | **维护者**: lanjiaxuan
