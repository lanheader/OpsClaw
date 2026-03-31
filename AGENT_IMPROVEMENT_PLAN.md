# OpsClaw Agent 体系改进计划

> 生成时间：2026-03-30
> 基于对项目代码的全面扫描和 Agent 架构深度分析

---

## 一、代码全面审查报告

### 综合评分：⭐⭐⭐ (3/5)

架构设计不错，但安全、测试、运维方面需要重点补强。

### 各维度评分

| 维度 | 评分 | 一句话 |
|------|------|--------|
| 架构设计 | ⭐⭐⭐⭐ | 分层清晰，文档完善 |
| 代码质量 | ⭐⭐⭐ | 有重复代码，错误处理不一致 |
| 安全性 | ⭐⭐⭐ | 有基础措施，但有命令注入和高危默认值 |
| 性能 | ⭐⭐⭐ | 动态创建Agent是瓶颈，SQLite限制并发 |
| 运维部署 | ⭐⭐ | 缺容器化、监控、配置验证 |
| 前端 | ⭐⭐⭐⭐ | 基础架构合理 |
| 测试 | ⭐ | 零测试，最大风险 |

---

### 🔴 必须立即修复的问题

#### 1. 命令注入漏洞（高危）
- **文件**: `app/tools/command_executor_tools.py`
- `execute_mysql_query` 和 `execute_redis_command` 用了 `shell=True` + 字符串拼接
- MySQL密码直接拼进命令行（`ps` 可见）
- query参数可能通过双引号转义注入
- **修复方案**：改用 `subprocess.run(cmd_list)`，密码走 stdin/环境变量

#### 2. 默认凭据硬编码
- **文件**: `app/core/config.py`
- JWT Secret 默认值 `"your-secret-key-here-change-in-production"`
- 管理员默认账号 `admin/admin123`
- **修复方案**：生产环境启动时强制检查，未设置则拒绝启动

#### 3. 命令白名单可绕过
- **文件**: `app/tools/command_executor_tools.py`
- `cat /proc/` 在白名单中，可读 `/proc/self/environ` 泄露密钥
- **修复方案**：收紧白名单，对 `/proc/` 路径做细粒度限制

#### 4. 测试覆盖率为 0
- `tests/` 目录是空的，对一个涉及命令执行、K8s操作、数据库查询的运维平台来说风险极高
- **修复方案**：至少先覆盖安全工具的白名单/黑名单测试和权限系统测试

---

### 🟡 重要改进建议

#### 架构层面
- **Agent 每次请求都重新创建**（`app/deepagents/main_agent.py` 注释："每次请求都重新创建 Agent"），高并发下是性能瓶颈 → 改为带 TTL 的缓存策略
- **`security.py` 和 `config.py` 重复定义配置** → 统一到 `get_settings()`
- **v1/v2 路由混用** → 制定清晰的 API 版本策略

#### 代码质量
- `execute_redis_command`、`execute_mysql_query`、`execute_safe_shell_command` 三个工具有 ~80% 重复代码 → 提取通用基础函数
- 错误处理不一致（有的返回字典，有的抛异常）→ 统一 `tool_error/success_response()`
- 全局异常处理在生产环境暴露了内部错误信息 `str(exc)`

#### 性能
- **会话锁内存泄漏**：`app/services/session_lock_manager.py` 中 `_session_locks` 字典没有定期清理 → 加 LRU/TTL 淘汰
- 多 worker 模式下内存锁失效 → 如需扩展，改用 Redis 分布式锁
- 权限查询每次 3 表 JOIN → 会话级缓存
- N+1 查询问题（`get_sessions` 逐个查统计）→ 改 JOIN/子查询

#### 运维部署
- **缺少 Dockerfile 和 docker-compose**
- 健康检查太简单（只检查 LLM）→ 增加数据库、飞书、K8s 状态检查
- 缺少优雅关闭逻辑 → 关闭连接池、等待进行中请求
- 缺少 Prometheus metrics 端点

#### 前端
- Token 存在 localStorage 有 XSS 风险 → 考虑 httpOnly cookie
- 缺少 React ErrorBoundary 全局错误处理

---

### 💡 新功能建议

1. **审计日志** — 记录所有工具调用、权限变更，支持查询导出
2. **API 限流** — 防止滥用
3. **工具执行沙箱** — 用容器隔离 shell 命令，与宿主机隔离
4. **告警 Webhook 入站** — 接 Prometheus AlertManager 自动触发诊断
5. **Agent 执行链路回放** — 可视化查看每次调用的完整流程
6. **多租户支持** — 多团队场景需要数据隔离
7. **定时巡检报告** — 利用 APScheduler 实现自动巡检
8. **OpenTelemetry 集成** — 分布式追踪 Agent 调用链

---

## 二、Agent 体系改进计划

### 当前架构核心问题

#### 问题 1：三子 Agent 太粗，缺少专业化细分

现在只有 data / analyze / execute 三个子 Agent，每个承担的职责太宽泛：
- **data-agent** 什么数据都采（K8s、Prometheus、Loki、Redis、MySQL），缺乏垂直领域专家
- **analyze-agent** 既要分析数据又要诊断问题又要给建议，能力边界模糊
- **execute-agent** 所有执行操作一把梭，没有区分操作类型

**需要新增的专业化 Agent：**

| Agent 名称 | 职责 | 对应工具 |
|-----------|------|---------|
| `network-agent` | 网络问题排查（DNS、Service 互通、Ingress、网络策略） | k8s.read + 诊断工具 |
| `storage-agent` | 存储问题处理（PVC、PV、磁盘空间、IO瓶颈） | k8s.read + 系统命令 |
| `security-agent` | 安全相关问题（RBAC、镜像扫描、证书过期、权限审计） | k8s.read + 专用工具 |
| `cost-agent` | 资源优化和成本分析（资源浪费、HPA建议、Spot实例） | prometheus + k8s.read |
| `incident-agent` | 事件管理和 OnCall（告警聚合、升级、通知、值班） | alert_tools + 飞书通知 |

**实现步骤：**
1. 在 `app/deepagents/subagents/` 下创建新的 Agent 配置文件
2. 在 `app/prompts/subagents/` 下创建对应的提示词
3. 在 `app/deepagents/subagents/__init__.py` 中注册新 Agent
4. 在 `app/tools/` 下按需添加专用工具
5. 更新主 Agent 的提示词，添加新 Agent 的说明和委派逻辑

---

#### 问题 2：缺少编排层和工作流引擎

目前主 Agent 是靠 prompt 来编排子 Agent 的，没有真正的流程控制：
- **没有 DAG 工作流** — 复杂场景需要多步骤、有依赖的执行链
- **没有并行调度** — data-agent 说支持 ReWOO 并行采集，但实际实现里是串行调工具
- **没有条件分支** — 分析结果决定下一步走哪条路，现在全靠 LLM "理解"
- **没有人工审批中断点** — `interrupt_on` 只在工具级别，缺少流程级别的审批网关

**修复方案：**

引入 LangGraph 的 `StateGraph` 做真正的状态机编排，替代纯 prompt 驱动：

```
用户输入 → 意图识别 → [条件分支]
                        ├── query   → data-agent → analyze-agent → 生成报告
                        ├── diagnose → data-agent → analyze-agent → [置信度检查]
                        │                                              ├── 高置信度 → 生成建议
                        │                                              └── 低置信度 → 补充采集 → 重新分析
                        └── operate  → analyze-agent → [审批网关]
                                                      ├── 批准 → execute-agent → 验证
                                                      └── 拒绝 → 终止
```

**实现步骤：**
1. 定义统一的 `AgentState` 类型（包含 messages、intent、data、analysis、plan 等字段）
2. 用 `StateGraph` 实现上述状态机
3. 在关键节点添加 `interrupt_before` 实现审批网关
4. 对 data-agent 的采集步骤实现真正的 `asyncio.gather` 并行调度
5. 替换 `get_ops_agent()` 中的 `create_deep_agent()` 为新的 StateGraph

---

#### 问题 3：缺少自我学习和知识沉淀闭环

`enhanced_*` 系列服务定义了 `lessons_learned`、`referenced_cases` 等字段，但：
- 分析完成后，经验**没有自动写入知识库**
- 下次遇到类似问题，不会自动 RAG 检索历史案例
- `MemoryManager` 存在但**没有被主流程串联起来**

**需要实现的闭环：**

```
诊断完成 → 提取关键信息(根因/方案/影响) → 写入 SQLite FTS5 知识库
                                              ↓
下次诊断 → LLM 分析用户问题 → 查询知识库相似案例 → 注入上下文 → 增强诊断
```

**具体实现：**

1. **在 `agent_chat_service.py` 的流程末尾**，当 intent_type 为 `diagnose` 且有诊断结果时：
   - 调用 `MemoryManager.remember_incident()` 保存经验
   - 提取字段：title、root_cause、resolution、incident_type、affected_resources

2. **在主 Agent 的 system_prompt 中**，添加知识库检索指令：
   - 诊断类问题先查知识库相似案例
   - 在分析中引用历史案例的解决方案

3. **在 `MemoryManager` 中新增**：
   - `search_similar_incidents(query, top_k=3)` — 搜索相似故障案例
   - `auto_extract_lessons(diagnosis_result)` — 从诊断结果自动提取经验

4. **构建故障模式库（Pattern Library）**：
   - 常见故障的标准化诊断路径（如 Pod CrashLoopBackOff 的 5 种常见原因 + 标准排查步骤）
   - 存储在 `app/memory/patterns/` 目录下，启动时加载

5. **Runbook 自动生成**：
   - 把成功修复经验固化为可复用的 Runbook
   - 支持从 Runbook 自动生成执行计划

---

#### 问题 4：缺少可观测性和调试能力

Agent 执行是个黑盒：
- 没有执行追踪 — 看不到每个子 Agent 的调用链、耗时、Token 消耗
- 没有执行回放 — 出了问题无法回放当时的决策过程
- 没有中间状态展示 — 用户只看到最终结果，看不到 Agent 在"想什么"
- 没有性能指标 — 不知道哪个 Agent 是瓶颈

**实现方案：**

1. **OpenTelemetry 集成**：
   - 在 `agent_chat_service.py` 中为每次 Agent 调用创建 Span
   - 在子 Agent 委派时创建子 Span
   - 在工具调用时记录 span attributes（工具名、参数、耗时、成功/失败）
   - 导出到 Jaeger 或 Tempo

2. **执行链路数据模型**：
   ```python
   @dataclass
   class AgentTrace:
       trace_id: str
       session_id: str
       user_query: str
       steps: List[AgentStep]  # 每一步的详细信息
       total_duration: float
       token_usage: dict
       final_result: str

   @dataclass
   class AgentStep:
       step_type: str  # "thinking" | "tool_call" | "subagent" | "response"
       agent_name: str
       input: str
       output: str
       duration: float
       token_count: int
       success: bool
   ```

3. **前端展示**：
   - 在 Chat 页面添加"执行详情"折叠面板
   - 展示每个步骤的耗时和状态
   - 支持"思考过程"的渐进式展示

4. **性能指标**：
   - 每个子 Agent 的平均响应时间
   - 工具调用成功率
   - Token 消耗统计
   - 会话完成率

---

#### 问题 5：缺少多轮对话和上下文管理

- 没有意图记忆 — 用户说"刚才那个 Pod"，Agent 不知道指哪个
- 没有会话摘要 — 长对话丢失上下文
- 没有任务恢复 — 中断了接不上
- `SessionLockManager` 只做了锁，没做状态恢复

**实现方案：**

1. **实体记忆（Entity Memory）**：
   - 在对话过程中提取并记住关键实体：namespace、pod_name、deployment_name、service_name
   - 用户后续说"重启它"、"看看它的日志"时，能自动补全实体
   - 存储在 checkpointer 的 state 中（不需要额外存储）

2. **会话摘要**：
   - 当会话消息数超过阈值（如 20 条）时，自动生成摘要
   - 摘要作为 SystemMessage 注入到后续对话中
   - `MemoryManager` 中已有 `SUMMARY_TRIGGER_THRESHOLD`，需要接入主流程

3. **任务恢复**：
   - 在 `SessionStateManager` 中保存当前任务的执行进度
   - 包含：已完成步骤、待执行步骤、中间数据
   - 用户说"继续"时，从断点恢复

4. **上下文引用**：
   - 支持用户说"刚才分析的 pod xxx"、"上一个问题"等指代表达
   - 在 prompt 中添加指令：遇到模糊引用时，回顾对话历史找到对应实体

---

#### 问题 6：缺少反馈和纠错机制

- Agent 诊断错了，用户只能重新描述问题
- 没有置信度校验 — `confidence: 0.85` 只是数字，不会触发二次确认
- 没有用户反馈收集 — 用户说"不对"之后没有学习机制
- 没有 A/B 评估 — 不知道哪个 prompt 策略更好

**实现方案：**

1. **置信度驱动的行为**：
   - `confidence < 0.6`：主动告诉用户"我不太确定"，建议补充信息
   - `confidence < 0.4`：自动补充数据采集后再给结论
   - `confidence > 0.9`：直接给出结论，不需要额外确认

2. **用户反馈收集**：
   - 在前端添加"诊断是否有帮助"的反馈按钮（👍/👎）
   - 反馈关联到具体的诊断记录
   - 存入数据库，用于后续评估和 prompt 优化

3. **自动纠错**：
   - 用户说"不对"、"不是这个原因"时，识别为否定反馈
   - 触发重新诊断，考虑用户补充的信息
   - 将错误诊断记录为"反模式"，避免重复

4. **Prompt 效果评估**：
   - 记录每次 Agent 调用的完整链路（输入 → 过程 → 输出 → 反馈）
   - 定期统计不同 prompt 版本的成功率
   - `UnifiedPromptOptimizer` 已有基础，需要接入评估数据

---

#### 问题 7：缺少定时和自动化能力

- 没有定时巡检 — prompt 里提到了但没有实现
- 没有告警自动触发 — `alert_tools.py` 返回的是硬编码假数据
- 没有 Cron Job — 无法设置"每天早上 9 点检查集群健康"
- 没有阈值自动响应 — CPU > 80% 自动扩容这种

**实现方案：**

1. **告警 Webhook 入站**（优先级最高）：
   - 新增 `app/api/v2/alert_webhook.py` 接收 AlertManager Webhook
   - 收到告警后自动触发诊断流程：
     - 解析告警（severity、labels、annotations）
     - 创建诊断会话
     - 自动委派 data-agent 采集相关数据
     - 自动委派 analyze-agent 诊断根因
     - 将结果通过飞书通知值班人员
   - 支持告警聚合：同一服务的多个告警合并为一次诊断

2. **定时巡检**：
   - 使用 APScheduler 实现定时任务
   - 支持自定义巡检计划（Cron 表达式）
   - 巡检内容：
     - 集群健康状态（Node、Pod 状态分布）
     - 资源使用率趋势（CPU、内存、磁盘）
     - 异常检测（CrashLoopBackOff、Pending、ImagePullBackOff）
     - 证书过期检查
   - 巡检报告通过飞书推送，支持订阅

3. **阈值自动响应**：
   - 支持配置响应规则：`当 CPU > 80% 持续 5 分钟 → 自动扩容`
   - 规则存储在数据库中，支持动态更新
   - 执行操作前需要审批（通过飞书确认）

4. **`alert_tools.py` 重构**：
   - 当前返回硬编码假数据，需要接入真实 AlertManager API
   - 新增 `app/integrations/alertmanager/client.py`

---

#### 问题 8：工具层缺失

当前工具覆盖不完整，运维平台缺少以下关键工具：

| 工具类别 | 缺失工具 | 用途 |
|---------|---------|------|
| Helm | `list_helm_releases`, `get_helm_history`, `rollback_helm_release` | 应用包管理 |
| Service Mesh | `get_istio_virtual_service`, `check_istio_proxy_status` | 流量管理 |
| CI/CD | `get_pipeline_status`, `trigger_pipeline` | 流水线管理 |
| Etcd | `get_etcd_health`, `get_etcd_key` | 集群排查 |
| 节点 | `check_docker_status`, `check_containerd_status` | 节点排查 |
| 证书 | `check_cert_expiry`, `get_cert_details` | 证书管理 |
| DNS | `check_dns_resolution`, `trace_dns` | 网络排查 |

**`execute_safe_shell_command` 改进**：
- 当前白名单太死板，应该支持**管理员自定义扩展**
- 增加正则表达式匹配模式（如 `kubectl.*` 而不是逐个命令）
- 增加命令审批机制：不在白名单的命令提交审批

---

## 三、实施路线图

### Phase 1 — 补齐核心能力（1-2周）

| 任务 | 优先级 | 涉及文件 |
|------|--------|---------|
| 🔴 修复命令注入漏洞 | P0 | `app/tools/command_executor_tools.py` |
| 🔴 强制安全配置（JWT Secret、管理员密码） | P0 | `app/core/config.py`, `app/main.py` |
| 🔴 补充安全工具测试 | P0 | 新建 `tests/test_command_executor_tools.py` |
| 🟡 enhanced 服务接入主流程 | P1 | `app/services/agent_chat_service.py` |
| 🟡 记忆闭环（分析完成自动沉淀经验） | P1 | `app/services/agent_chat_service.py`, `app/memory/memory_manager.py` |
| 🟡 Agent 执行链路追踪 | P1 | 新建 `app/tracing/`, 修改 `agent_chat_service.py` |
| 🟡 多轮上下文管理（会话摘要 + 实体记忆） | P1 | `app/memory/memory_manager.py`, 主 Agent prompt |

### Phase 2 — 专业化拆分（2-3周）

| 任务 | 优先级 | 涉及文件 |
|------|--------|---------|
| 🟡 拆出 network-agent | P1 | 新建 `app/deepagents/subagents/network_agent.py` |
| 🟡 拆出 storage-agent | P1 | 新建 `app/deepagents/subagents/storage_agent.py` |
| 🟡 DAG 工作流引擎（LangGraph StateGraph） | P1 | 重构 `app/deepagents/main_agent.py` |
| 🟡 真正的并行调度 | P1 | 修改 `app/services/enhanced_data_agent_service.py` |
| 🟡 告警 Webhook 入站 | P1 | 新建 `app/api/v2/alert_webhook.py`, `app/integrations/alertmanager/` |
| 🟡 alert_tools 接入真实 AlertManager | P2 | 重构 `app/tools/alert_tools.py` |

### Phase 3 — 自动化闭环（3-4周）

| 任务 | 优先级 | 涉及文件 |
|------|--------|---------|
| 🟢 定时巡检 | P2 | 新建 `app/services/patrol_service.py` |
| 🟢 阈值自动响应 | P2 | 新建 `app/services/auto_response_service.py` |
| 🟢 Runbook 自动生成 | P2 | 新建 `app/services/runbook_service.py` |
| 🟢 用户反馈 + 置信度校验 | P2 | 修改 `agent_chat_service.py`, 前端 |
| 🟢 补充工具（Helm、证书、DNS） | P2 | 新建 `app/tools/` 下对应文件 |
| 🟢 Dockerfile + docker-compose | P2 | 新建项目根目录文件 |

### Phase 4 — 打磨优化（持续）

| 任务 | 优先级 | 涉及文件 |
|------|--------|---------|
| 🟢 补充测试覆盖（目标 60%） | P2 | `tests/` |
| 🟢 API 限流 | P3 | `app/middleware/` |
| 🟢 工具执行沙箱 | P3 | 新建 `app/sandbox/` |
| 🟢 审计日志 | P3 | 新建 `app/services/audit_service.py` |
| 🟢 多租户支持 | P3 | 架构级改造 |

---

## 四、参考文件清单

### 核心文件（改动涉及）

```
app/deepagents/
├── main_agent.py              # 主 Agent 创建和配置
├── factory.py                 # Agent 工厂（兼容层）
├── component_cache.py         # 组件缓存
└── subagents/
    ├── __init__.py            # 子 Agent 注册
    ├── analyze_agent.py       # 分析 Agent
    ├── data_agent.py          # 数据采集 Agent
    └── execute_agent.py       # 执行 Agent

app/services/
├── agent_chat_service.py      # 统一消息处理（核心入口）
├── enhanced_analyze_service.py    # 增强分析服务
├── enhanced_data_agent_service.py # 增强数据采集服务
├── enhanced_execute_service.py    # 增强执行服务
├── enhanced_main_agent_service.py # 增强主 Agent 服务
├── session_lock_manager.py    # 会话锁
└── session_state_manager.py   # 会话状态管理

app/tools/
├── command_executor_tools.py  # 命令执行工具（安全漏洞）
├── alert_tools.py             # 告警工具（假数据）
├── k8s/                       # K8s 工具
├── prometheus/                # Prometheus 工具
└── loki/                      # Loki 工具

app/memory/
├── memory_manager.py          # 记忆管理器
├── sqlite_fts_store.py        # SQLite 全文搜索
└── sqlite_memory_store.py     # SQLite 记忆存储

app/prompts/
├── main_agent.py              # 主 Agent 提示词
└── subagents/                 # 子 Agent 提示词
    ├── analyze.py
    ├── data.py
    └── execute.py

app/core/
├── config.py                  # 配置（默认凭据）
├── security.py                # 安全（重复配置）
└── llm_factory.py             # LLM 工厂
```

### 需要新建的文件

```
app/deepagents/subagents/
├── network_agent.py           # 网络 Agent
├── storage_agent.py           # 存储 Agent
├── security_agent.py          # 安全 Agent
├── cost_agent.py              # 成本 Agent
└── incident_agent.py          # 事件 Agent

app/prompts/subagents/
├── network.py                 # 网络 Agent 提示词
├── storage.py                 # 存储 Agent 提示词
├── security.py                # 安全 Agent 提示词
├── cost.py                    # 成本 Agent 提示词
└── incident.py                # 事件 Agent 提示词

app/integrations/alertmanager/
└── client.py                  # AlertManager 客户端

app/api/v2/
└── alert_webhook.py           # 告警 Webhook 入口

app/services/
├── patrol_service.py          # 巡检服务
├── auto_response_service.py   # 自动响应服务
├── runbook_service.py         # Runbook 服务
└── audit_service.py           # 审计日志服务

app/tracing/
├── __init__.py
├── tracer.py                  # OpenTelemetry 配置
└── trace_models.py            # 链路数据模型

app/memory/patterns/           # 故障模式库
├── __init__.py
├── pod_crash.json             # Pod CrashLoopBackOff 模式
├── oom_kill.json              # OOM Killed 模式
├── network_timeout.json       # 网络超时模式
└── disk_full.json             # 磁盘满模式

app/tools/
├── helm/                      # Helm 工具
├── certificate/               # 证书工具
└── dns/                       # DNS 工具

tests/
├── test_command_executor_tools.py  # 安全工具测试
├── test_permissions.py            # 权限系统测试
├── test_agent_workflow.py          # Agent 工作流测试
└── test_memory_manager.py          # 记忆系统测试

Dockerfile                      # 容器化配置
docker-compose.yml              # 编排配置
```
