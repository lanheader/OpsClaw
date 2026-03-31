# OpsClaw Agent 体系改进计划 V2

> 生成时间：2026-03-30
> 基于 deepagents v0.4.12 框架能力，结合 OpsClaw 动态权限/审批场景

---

## 一、核心诊断：在和框架对着干

OpsClaw 基于 deepagents v0.4.12，但大量能力没有利用，同时又重复造轮子。

### 1.1 deepagents 内置能力 vs OpsClaw 现状

| deepagents 内置能力 | OpsClaw 现状 | 问题 |
|---|---|---|
| `SummarizationMiddleware` — LLM 智能摘要，自动压缩长对话 | 自写了 `MessageTrimmingMiddleware`，只做简单截断丢消息 | 信息丢失，上下文断裂 |
| `MemoryMiddleware` — 自动加载 AGENTS.md 到 system prompt | 自建了 `MemoryManager` + `SQLiteMemoryStore`，但没接入这个中间件 | 记忆和 Agent 执行割裂 |
| `SkillsMiddleware` — 技能渐进式加载（先元数据，按需加载全文） | 传了 `skills=["skills/"]` 但目录是空的 | 零技能加载 |
| `HumanInTheLoopMiddleware` — 审批中断 | 传了 `interrupt_on`，同时自建了 `ApprovalConfigService` | 重复逻辑 |
| 内置 `execute` 工具（需 `SandboxBackendProtocol`） | 自建了 `execute_safe_shell_command` + 白名单 | 内置 execute 不可用 |
| 内置文件工具 `ls/read_file/write_file/edit_file/glob/grep` | 未利用 | Agent 不能生成报告、写 Runbook |
| SubAgent 自动继承完整中间件栈 | 每个 SubAgent 又手动指定中间件 | 重复配置 |
| SubAgent 自带 ReAct 循环（思考→工具→观察→再思考） | 自建了 `enhanced_*_service.py` 手写 ReWOO/ReAct/ToT | 重复实现 |

### 1.2 动态权限/审批与框架的冲突

deepagents 的 `create_deep_agent()` 是**创建时绑定**的（tools、interrupt_on、middleware 在创建时固定），但 OpsClaw 需要**运行时动态**（每个用户不同权限，审批配置可能随时变化）。

当前解决方案：每次请求重建整个 Agent（`get_ops_agent()` 注释："每次请求都重新创建 Agent"）。这能工作但代价大。

**正确做法：Agent 图创建一次，动态权限/审批放在自定义 middleware 层解决。**

---

## 二、改进任务清单

### 任务 1：实现动态权限 Middleware（核心基础设施）

**目标**：将权限检查从 Agent 创建时移到工具调用时，实现"一次创建、动态过滤"。

**新建文件**：`app/middleware/dynamic_permission_middleware.py`

**实现要求**：

```python
"""
动态权限中间件

职责：
- 在工具调用前检查当前用户是否有权限
- 无权限的工具调用直接拦截返回错误
- 每次请求实例化，携带当前用户的权限集合

使用方式：
    middleware = DynamicPermissionMiddleware(permissions={"k8s.read", "prometheus.query"})
```

from langchain.agents.middleware.types import AgentMiddleware

class DynamicPermissionMiddleware(AgentMiddleware):
    def __init__(self, permissions: set):
        """
        Args:
            permissions: 当前用户拥有的权限代码集合
                         如 {"k8s.read", "prometheus.query", "k8s.write"}
        """
        self.permissions = permissions

    async def awrap_tool_call(self, request, handler):
        """
        在工具调用前拦截，检查权限。

        工具名到权限的映射规则：
        - 工具的 metadata.group 对应权限代码
        - 如果用户拥有对应 group 的权限，放行
        - 否则返回权限不足的错误

        需要从 app/tools/registry.py 中的 ToolRegistry 获取工具的 group 信息。
        """
        tool_name = request.tool_name

        # 1. 从 ToolRegistry 获取工具所需的权限 group
        #    registry = get_tool_registry()
        #    tool_class = registry.get_tool(tool_name)
        #    required_permission = tool_class.get_metadata().group if tool_class else None

        # 2. 检查用户是否有该权限
        #    if required_permission and required_permission not in self.permissions:
        #        return error response

        # 3. 有权限，放行
        return await handler(request)
```

**注意事项**：
- 需要查看 `langchain.agents.middleware.types.AgentMiddleware` 的 `awrap_tool_call` 签名，确保兼容
- `ToolRegistry.get_tool(tool_name)` 返回工具类，工具类的 `get_metadata()` 返回 `ToolMetadata`，其中有 `group` 字段
- 权限代码格式参考 `app/core/permissions.py` 中的定义
- 对于没有在 registry 中注册的工具（如 deepagents 内置的 `write_todos`、`task` 等），默认放行

---

### 任务 2：实现动态审批 Middleware

**目标**：将审批检查从 `interrupt_on`（创建时固定）移到 middleware（运行时动态）。

**新建文件**：`app/middleware/dynamic_approval_middleware.py`

**实现要求**：

```python
"""
动态审批中间件

职责：
- 在工具调用前动态查询数据库，判断该工具是否需要审批
- 需要审批时，暂停 Agent 执行，等待用户确认
- 支持按角色配置不同的审批策略

使用方式：
    middleware = DynamicApprovalMiddleware(user_id=1, db_session=db)
```

from langchain.agents.middleware.types import AgentMiddleware

class DynamicApprovalMiddleware(AgentMiddleware):
    def __init__(self, user_id: int, db_session):
        """
        Args:
            user_id: 当前用户 ID
            db_session: 数据库会话
        """
        self.user_id = user_id
        # 从数据库加载当前用户的审批配置
        # 复用 app/services/approval_config_service.py 的逻辑
        self.tools_need_approval = self._load_approval_config(db_session)

    async def awrap_tool_call(self, request, handler):
        """
        在工具调用前检查是否需要审批。

        如果需要审批：
        - 使用 LangGraph 的 interrupt 机制暂停执行
        - 将审批请求信息传递给前端
        - 等待用户确认后恢复执行

        实现方式：
        - LangGraph 中断：在 State 中写入审批状态
        - 或者：使用 deepagents 的 HumanInTheLoopMiddleware 的 interrupt 机制

        注意：需要研究 LangGraph 的 interrupt API，
        确保能在自定义 middleware 中触发中断。
        """
        tool_name = request.tool_name

        if tool_name in self.tools_need_approval:
            # 触发审批中断
            # 具体实现需要研究 LangGraph interrupt 机制
            pass

        return await handler(request)

    def _load_approval_config(self, db_session) -> set:
        """
        从数据库加载审批配置。

        复用 app/services/approval_config_service.py 的逻辑：
        - ApprovalConfigService.get_tools_require_approval(db, user_role=...)
        - 获取当前用户的角色
        - 根据角色获取需要审批的工具列表
        """
        pass
```

**注意事项**：
- 需要研究 LangGraph 的 `interrupt` API，确认能否在自定义 middleware 中触发
- 参考 `deepagents.middleware.human_in_the_loop.HumanInTheLoopMiddleware` 的实现
- 如果 LangGraph 不支持在 middleware 中触发 interrupt，备选方案是：在 `before_model` 阶段往 state 中写入审批标记，然后在 `after_tool` 阶段检查并中断
- 审批数据格式参考 `app/services/session_state_manager.py` 中的 `AWAITING_APPROVAL` 状态

---

### 任务 3：重构 Agent 创建逻辑——静态创建一次

**目标**：Agent 图只创建一次（或按 LLM 配置缓存），不再每次请求重建。

**修改文件**：`app/deepagents/main_agent.py`

**实现要求**：

1. 新增 `create_base_agent()` 函数，在应用启动时调用一次：

```python
async def create_base_agent() -> CompiledStateGraph:
    """
    创建基础 Agent（应用启动时调用一次）。

    特点：
    - 加载所有工具（不做权限过滤）
    - 加载所有 SubAgent
    - 不设置 interrupt_on（由 DynamicApprovalMiddleware 处理）
    - 配置 Skills、Memory、Filesystem 等 deepagents 内置能力
    """
    llm = LLMFactory.create_llm()
    checkpointer = await get_checkpointer()
    store = get_langgraph_store()

    # 所有工具（不过滤权限）
    registry = get_tool_registry()
    all_tools = registry.get_langchain_tools()

    # 所有 SubAgent
    all_subagents = get_all_subagents()

    # deepagents 内置能力配置
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    backend = FilesystemBackend(root_dir=project_root, virtual_mode=False)

    agent = create_deep_agent(
        name="OpsAgent",
        model=llm,
        system_prompt=MAIN_AGENT_SYSTEM_PROMPT,
        tools=all_tools,
        subagents=all_subagents,
        middleware=[
            # 自定义 middleware（不含权限/审批逻辑）
            ErrorFilteringMiddleware(),
            LoggingMiddleware(),
        ],
        checkpointer=checkpointer,
        store=store,
        backend=backend,
        skills=["skills/"],
        # 不传 interrupt_on，由 DynamicApprovalMiddleware 处理
    )

    return agent
```

2. 修改 `get_ops_agent()` 为轻量包装：

```python
async def get_ops_agent(
    user_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> Any:
    """
    获取 Agent 实例（轻量包装）。

    不再重建 Agent 图，而是返回带动态 middleware 的包装器。
    """
    base_agent = get_cached_base_agent()  # 从缓存获取

    if user_id and db:
        # 获取用户权限
        permissions = _get_user_permissions(user_id, db)
        # 创建动态包装器
        return DynamicAgentWrapper(
            base_agent=base_agent,
            permission_middleware=DynamicPermissionMiddleware(permissions),
            approval_middleware=DynamicApprovalMiddleware(user_id, db),
        )
    else:
        return base_agent
```

3. `DynamicAgentWrapper` 实现：

```python
class DynamicAgentWrapper:
    """
    Agent 动态包装器。

    将 base_agent 和动态 middleware 组合，
    在每次调用时注入当前请求的权限和审批配置。
    """
    def __init__(self, base_agent, permission_middleware, approval_middleware):
        self._agent = base_agent
        self._permission_middleware = permission_middleware
        self._approval_middleware = approval_middleware

    async def ainvoke(self, input_data, config=None, **kwargs):
        # 在调用前注入动态 middleware
        # 具体实现取决于 langchain middleware 的注入方式
        return await self._agent.ainvoke(input_data, config=config, **kwargs)

    async def astream(self, input_data, config=None, **kwargs):
        return self._agent.astream(input_data, config=config, **kwargs)
```

**注意事项**：
- `get_cached_base_agent()` 需要一个全局缓存变量，应用启动时设置
- 需要研究 langchain middleware 的动态注入机制——是每次创建新的 agent 实例，还是有运行时 middleware 注入 API
- 如果 langchain 不支持运行时注入 middleware，备选方案是：保留"按权限组合缓存 Agent 实例"的策略（类似现在的 `ComponentCache`），但缓存的是编译后的 Agent 图而非每次重建
- `app/main.py` 中的 startup 事件需要调用 `create_base_agent()` 预热

---

### 任务 4：删除冗余的 MessageTrimmingMiddleware

**目标**：用 deepagents 内置的 `SummarizationMiddleware` 替换自定义截断。

**操作**：

1. **删除文件**：`app/middleware/message_trimming_middleware.py`
2. **修改**：`app/deepagents/component_cache.py` 中 `_load_middleware()` 方法，移除 `MessageTrimmingMiddleware(max_messages=40)`
3. **验证**：确认 deepagents 内置的 `SummarizationMiddleware` 已经在 `create_deep_agent()` 中自动注入，不需要额外配置
4. **可选调优**：如果默认的摘要触发阈值不合适，可以通过 `create_deep_agent()` 的 middleware 参数传入自定义配置的 `SummarizationMiddleware` 来覆盖默认行为

---

### 任务 5：填充 Skills 目录

**目标**：把运维知识写成 Skills 文件，利用 deepagents 的 `SkillsMiddleware` 渐进式加载。

**新建文件**：

```
skills/
├── k8s-troubleshooting/
│   └── SKILL.md
├── pod-crashloop/
│   └── SKILL.md
├── network-debugging/
│   └── SKILL.md
├── resource-analysis/
│   └── SKILL.md
└── incident-response/
    └── SKILL.md
```

**每个 SKILL.md 的格式要求**：

```markdown
---
description: 简短描述（SkillsMiddleware 会先加载这个用于元数据展示）
---

# 技能标题

## 适用场景
什么时候需要用这个技能

## 标准排查流程
1. 步骤一
2. 步骤二
3. ...

## 常见模式
- 模式A：症状 → 原因 → 方案
- 模式B：症状 → 原因 → 方案

## 命令参考
- `kubectl xxx` — 用途说明
- `xxx` — 用途说明

## 注意事项
- ...
```

**内容要求**（以 `pod-crashloop/SKILL.md` 为例）：

```markdown
---
description: Pod CrashLoopBackOff 标准排查路径，覆盖 5 种常见原因
---

# Pod CrashLoopBackOff 排查

## 适用场景
Pod 状态为 CrashLoopBackOff 或频繁 Restart

## 排查流程

### Step 1: 获取 Pod 状态和事件
```
kubectl describe pod <pod-name> -n <namespace>
kubectl get events --field-selector involvedObject.name=<pod-name> -n <namespace>
```

### Step 2: 查看容器日志
```
kubectl logs <pod-name> -n <namespace> --previous
```

### Step 3: 根据日志定位原因

#### 原因 1: 应用启动失败（最常见）
- 症状：日志显示 "Connection refused"、"Failed to connect to xxx"
- 排查：检查依赖服务是否正常运行
- 修复：修复依赖服务，或调整启动顺序（init container）

#### 原因 2: 配置错误
- 症状：日志显示 "config file not found"、"invalid config"
- 排查：检查 ConfigMap/Secret 是否挂载，内容是否正确
- 修复：更新 ConfigMap/Secret

#### 原因 3: 资源不足（OOMKilled）
- 症状：Events 显示 OOMKilled，Last State 中 Exit Code 137
- 排查：检查 Pod 的 resources.limits，对比实际使用量
- 修复：增加内存 limit，或优化应用内存使用

#### 原因 4: 镜像问题
- 症状：Events 显示 ImagePullBackOff 或 ErrImagePull
- 排查：检查镜像名、tag、仓库凭证
- 修复：修正镜像配置或添加 imagePullSecrets

#### 原因 5: 健康检查失败
- 症状：Events 显示 Liveness probe failed
- 排查：检查 livenessProbe/readinessProbe 配置，应用健康端点是否正常
- 修复：调整探针配置（initialDelaySeconds、timeoutSeconds、failureThreshold）

### Step 4: 验证修复
```
kubectl get pod <pod-name> -n <namespace> -w
kubectl logs <pod-name> -n <namespace> -f
```
```

**其他 Skills 内容参考**：
- `k8s-troubleshooting/SKILL.md` — 通用 K8s 故障排查框架（Node NotReady、Pod Pending、Service 无端点等）
- `network-debugging/SKILL.md` — DNS 解析失败、Service 互通、Ingress 不工作、网络策略排查
- `resource-analysis/SKILL.md` — CPU/内存/磁盘使用率分析、资源浪费识别、HPA 配置建议
- `incident-response/SKILL.md` — 事件分级（P0-P3）、响应流程、升级策略、通知模板

---

### 任务 6：接入 MemoryMiddleware，打通知识库

**目标**：让 Agent 在每次对话时自动加载相关知识。

**实现方式**：

在 `create_base_agent()` 中使用 deepagents 的 `memory` 参数：

```python
agent = create_deep_agent(
    ...,
    memory=["/memory/AGENTS.md"],
)
```

**但需要动态化**：OpsClaw 的知识是从 SQLite FTS5 查询的，不是静态文件。

**解决方案**：

1. 在 `app/memory/` 下创建一个动态生成 AGENTS.md 内容的函数：

```python
# app/memory/dynamic_memory.py

async def generate_dynamic_memory(user_query: str = None) -> str:
    """
    动态生成 Agent 记忆内容。

    策略：
    1. 始终加载：系统基本信息（集群名称、环境等）
    2. 按需加载：根据用户查询，从知识库检索相关经验
    3. 最近经验：最近 N 条故障诊断经验
    """
    memory_manager = get_memory_manager()

    sections = []

    # 1. 系统基本信息（固定）
    sections.append("## 集群信息\n")
    sections.append("- 环境: 生产/测试\n")
    sections.append("- K8s 版本: ...\n")

    # 2. 相关历史经验（按查询检索或取最近 N 条）
    if user_query:
        similar = memory_manager.search_similar_incidents(user_query, top_k=3)
        if similar:
            sections.append("\n## 相关历史经验\n")
            for case in similar:
                sections.append(f"### {case.title}\n")
                sections.append(f"- 根因: {case.root_cause}\n")
                sections.append(f"- 方案: {case.resolution}\n")

    return "\n".join(sections)
```

2. **两种接入路径**（根据 deepagents 的 memory 参数机制选择）：

   **路径 A**：如果 `memory` 参数支持文件路径，在每次请求前把动态内容写到文件：
   ```python
   memory_content = await generate_dynamic_memory(user_query)
   memory_path = "/tmp/opsclaw_memory/AGENTS.md"
   os.makedirs(os.path.dirname(memory_path), exist_ok=True)
   with open(memory_path, "w") as f:
       f.write(memory_content)
   # 然后把 memory_path 传给 create_deep_agent
   ```

   **路径 B**：如果 memory 是创建时固定的，在自定义 middleware 的 `awrap_model_call` 中手动注入：
   ```python
   class DynamicMemoryMiddleware(AgentMiddleware):
       async def awrap_model_call(self, request, handler):
           # 在 system message 末尾追加动态知识
           memory_content = await generate_dynamic_memory()
           # 修改 request 的 system message
           return await handler(modified_request)
   ```

**注意事项**：
- 先研究 deepagents `MemoryMiddleware` 的源码，确认它是在 `before_agent` 时一次性加载还是每次 model call 都加载
- 如果是一次性加载，用路径 A（动态写文件）；如果是每次 model call 都加载，用路径 B 更高效
- 知识检索不能太慢，否则增加请求延迟。SQLite FTS5 的 BM25 查询应该足够快（< 50ms）

---

### 任务 7：SubAgent 专业化拆分

**目标**：在 deepagents 框架内添加专业化 SubAgent，只需 dict 配置。

**新建文件**：

```
app/deepagents/subagents/network_agent.py
app/deepagents/subagents/storage_agent.py
app/deepagents/subagents/security_agent.py

app/prompts/subagents/network.py
app/prompts/subagents/storage.py
app/prompts/subagents/security.py
```

**每个 SubAgent 的结构**（以 network_agent 为例）：

```python
# app/deepagents/subagents/network_agent.py

from app.tools import get_tools_by_group

NETWORK_AGENT_CONFIG = {
    "name": "network-agent",
    "description": "排查网络问题：DNS解析、Service互通、Ingress配置、网络策略。当用户提到网络不通、DNS失败、服务间调用超时、Ingress 404/502 时使用。",
    "system_prompt": None,  # 从 prompts/subagents/network.py 加载
    "tools": [
        *get_tools_by_group("k8s.read"),
        # 如果有网络专用工具也加在这里
    ],
    # 注意：不需要指定 middleware、model
    # deepagents 会自动注入完整的中间件栈
    # model 如果需要用不同的 LLM，可以在这里指定
    # "model": "deepseek:deepseek-chat",
}
```

```python
# app/prompts/subagents/network.py

NETWORK_AGENT_PROMPT = """
<language_requirement>
你必须始终使用中文回复。
</language_requirement>

<role>
你是 **Network Agent**，K8s 网络问题排查专家。
</role>

<core_principles>
1. 先确认问题现象（DNS? 连接超时? 502?）
2. 从 CoreDNS → Service → Pod 逐层排查
3. 每个结论用工具验证，不猜测
</core_principles>

<common_patterns>
## DNS 解析失败
1. 检查 CoreDNS Pod 状态
2. 检查 CoreDNS 日志
3. 检查 Pod 的 dnsPolicy 和 dnsConfig
4. 用 nslookup 测试解析

## Service 不可达
1. 检查 Service 的 selector 是否匹配 Pod labels
2. 检查 Endpoints 是否有 IP
3. 检查 targetPort 是否正确
4. 在 Pod 内用 curl 测试

## Ingress 问题
1. 检查 Ingress 规则（host、path）
2. 检查 Ingress Controller 日志
3. 检查后端 Service 是否有 Endpoints
</common_patterns>

<output_format>
按以下格式输出：
- 问题现象
- 排查步骤（每步附工具调用结果）
- 根因分析
- 修复建议
</output_format>
"""
```

**注册方式**：修改 `app/deepagents/subagents/__init__.py`

```python
from .network_agent import NETWORK_AGENT_CONFIG
from .storage_agent import STORAGE_AGENT_CONFIG
from .security_agent import SECURITY_AGENT_CONFIG

def get_all_subagents() -> List[SubAgent]:
    configs = [
        DATA_AGENT_CONFIG.copy(),
        ANALYZE_AGENT_CONFIG.copy(),
        EXECUTE_AGENT_CONFIG.copy(),
        NETWORK_AGENT_CONFIG.copy(),   # 新增
        STORAGE_AGENT_CONFIG.copy(),   # 新增
        SECURITY_AGENT_CONFIG.copy(),  # 新增
    ]
    # ... 后续注入 prompt 和 model 的逻辑不变
```

**注意事项**：
- 不需要为每个新 Agent 写 `enhanced_*_service.py`——deepagents 的 SubAgent 本身就是 ReAct 循环
- 主 Agent 的 `MAIN_AGENT_SYSTEM_PROMPT` 需要更新，添加新 Agent 的说明，让主 Agent 知道什么时候该委派给哪个 Agent
- SubAgent 的 `description` 非常重要——主 Agent 根据它决定是否委派，描述要具体、包含触发关键词

---

### 任务 8：利用内置文件工具让 Agent 生成产出物

**目标**：Agent 分析完可以生成报告、Runbook 等文件。

**实现方式**：

deepagents 内置了 `write_file`、`read_file` 等文件工具（通过 `FilesystemMiddleware`）。因为 OpsClaw 已经配置了 `FilesystemBackend(root_dir=project_root)`，Agent 可以在项目目录下读写文件。

**需要做的**：

1. 在主 Agent 的 `system_prompt` 中添加文件输出指令：

```
<file_output>
完成分析后，你可以使用 `write_file` 工具生成报告：
- 诊断报告保存到: /reports/{date}/{session_id}_diagnosis.md
- Runbook 保存到: /runbooks/{problem_type}.md
- 分析数据导出到: /exports/{session_id}_data.json

报告格式使用 Markdown，包含：问题摘要、根因分析、证据、修复建议、验证步骤。
</file_output>
```

2. 确保文件目录存在且有写权限：

```python
# app/main.py startup 中
os.makedirs("/data/apps/OpsClaw/reports", exist_ok=True)
os.makedirs("/data/apps/OpsClaw/runbooks", exist_ok=True)
os.makedirs("/data/apps/OpsClaw/exports", exist_ok=True)
```

3. （可选）在前端添加"下载报告"按钮，读取 `/reports/` 下的文件

---

### 任务 9：清理冗余代码

**目标**：移除与 deepagents 内置能力重复的代码。

**可删除的文件/模块**：

| 文件 | 替代方案 | 删除前提 |
|---|---|---|
| `app/middleware/message_trimming_middleware.py` | deepagents `SummarizationMiddleware` | 任务 4 完成后 |
| `app/services/enhanced_main_agent_service.py` | 主 Agent 自身已有 CoT 能力 | 确认主 Agent prompt 足够好 |
| `app/services/enhanced_data_agent_service.py` | data-agent 自身已有 ReAct 循环 | 确认 data-agent prompt 足够好 |
| `app/services/enhanced_analyze_service.py` | analyze-agent 自身已有推理链 | 确认 analyze-agent prompt 足够好 |
| `app/services/enhanced_execute_service.py` | execute-agent 自身已有验证循环 | 确认 execute-agent prompt 足够好 |

**注意**：删除前要确认这些 service 中是否有被其他模块引用的核心逻辑（如 `lessons_learned`、`referenced_cases` 的提取逻辑），如果有需要迁移到其他地方（如任务 6 的 `DynamicMemoryMiddleware` 中）。

**可简化的代码**：

| 文件 | 简化内容 |
|---|---|
| `app/deepagents/factory.py` | `FinalReportEnrichedAgent` 包装可以移除，改用 prompt 约束 |
| `app/deepagents/component_cache.py` | 如果任务 3 实现"静态创建一次"，此文件大幅简化，只需缓存 base_agent |
| `app/deepagents/main_agent.py` | `_build_system_prompt()` 中的审批工具列表拼接可以移除（由 middleware 处理） |

---

### 任务 10：安全漏洞修复（必须）

这些和框架无关，但必须修：

#### 10.1 命令注入漏洞
**文件**：`app/tools/command_executor_tools.py`

- `execute_mysql_query` 和 `execute_redis_command` 使用 `shell=True` + 字符串拼接
- 修复：改用 `subprocess.run(cmd_list)`，不用 `shell=True`
- MySQL 密码不要通过命令行参数传递（`-p{password}` 在 `ps` 中可见），改用 `MYSQL_PWD` 环境变量或 `--defaults-extra-file`
- Redis 密码同理，改用 `REDISCLI_AUTH` 环境变量

#### 10.2 默认凭据
**文件**：`app/core/config.py`

- JWT Secret 默认值 `"your-secret-key-here-change-in-production"`
- 管理员默认 `admin/admin123`
- 修复：在 `app/main.py` 的 startup 中检查，如果使用默认值且 `ENVIRONMENT != "dev"`，拒绝启动并报错

#### 10.3 命令白名单收紧
**文件**：`app/tools/command_executor_tools.py`

- `cat /proc/` 可读 `/proc/self/environ` 泄露密钥
- 修复：对 `cat /proc/` 限制为白名单路径（如 `/proc/cpuinfo`、`proc/meminfo`），禁止 `/proc/self/`、`/proc/<pid>/environ`

#### 10.4 全局异常处理
**文件**：`app/main.py`

- `global_exception_handler` 在生产环境暴露了 `str(exc)`
- 修复：根据 `DEBUG` 配置决定是否返回详细错误

---

### 任务 11：alert_tools.py 重构

**文件**：`app/tools/alert_tools.py`

**当前问题**：所有函数返回硬编码假数据，没有任何实际功能。

**实现要求**：

1. 新建 `app/integrations/alertmanager/client.py`：
   - 封装 AlertManager API 调用
   - `get_alerts()` — 获取活跃告警
   - `get_silences()` — 获取静默规则
   - `create_silence()` — 创建静默
   - AlertManager 地址从 `app/core/config.py` 读取

2. 重构 `alert_tools.py`，调用真实 API

3. 新建 `app/api/v2/alert_webhook.py`：
   - 接收 AlertManager Webhook
   - 自动创建诊断会话
   - 委派 data-agent + analyze-agent 诊断
   - 通过飞书通知结果

---

## 三、执行顺序

```
Phase 1（基础设施，先做）：
├── 任务 10：安全漏洞修复
├── 任务 1：DynamicPermissionMiddleware
├── 任务 2：DynamicApprovalMiddleware
└── 任务 3：重构 Agent 创建逻辑（依赖任务 1、2）

Phase 2（能力提升）：
├── 任务 4：删除 MessageTrimmingMiddleware
├── 任务 5：填充 Skills 目录
├── 任务 6：接入 MemoryMiddleware
└── 任务 8：利用内置文件工具

Phase 3（扩展）：
├── 任务 7：SubAgent 专业化拆分
├── 任务 11：alert_tools 重构
└── 任务 9：清理冗余代码（最后做，确保前面的都稳定后）
```

## 四、关键参考

### deepagents 框架 API（v0.4.12）

```python
from deepagents import create_deep_agent, SubAgent
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.middleware import (
    SummarizationMiddleware,
    MemoryMiddleware,
    SkillsMiddleware,
)

# 创建 Agent
agent = create_deep_agent(
    model="provider:model-name",        # LLM
    system_prompt="...",                 # 自定义 prompt（会拼接到 BASE_AGENT_PROMPT 前面）
    tools=[...],                         # 工具列表
    subagents=[{                         # SubAgent 配置
        "name": "xxx",
        "description": "...",            # 主 Agent 根据这个决定是否委派
        "system_prompt": "...",
        "tools": [...],                  # 可选，不传则继承主 Agent 工具
        "model": "...",                  # 可选，覆盖主 Agent 模型
        "middleware": [...],              # 可选，追加到自动注入的中间件之后
        "skills": [...],                 # 可选，该 SubAgent 专属 Skills
        "interrupt_on": {...},           # 可选，该 SubAgent 的审批配置
    }],
    middleware=[...],                     # 追加到主 Agent 内置中间件之后
    skills=["skills/"],                  # Skills 目录
    memory=["/memory/AGENTS.md"],        # 记忆文件
    checkpointer=...,                    # 状态持久化
    store=...,                           # 持久存储
    backend=FilesystemBackend(...),      # 文件后端
    interrupt_on={...},                  # 审批配置
)
```

### SubAgent 自动注入的中间件栈（不需要手动指定）

1. `TodoListMiddleware` — 任务规划
2. `FilesystemMiddleware` — 文件操作
3. `SummarizationMiddleware` — 对话压缩
4. `AnthropicPromptCachingMiddleware` — prompt 缓存
5. `PatchToolCallsMiddleware` — 工具调用修补
6. （可选）`SkillsMiddleware` — 如果指定了 skills
7. （可选）用户自定义 middleware

### 主 Agent 自动注入的中间件栈

1. `TodoListMiddleware`
2. （可选）`MemoryMiddleware` — 如果指定了 memory
3. （可选）`SkillsMiddleware` — 如果指定了 skills
4. `FilesystemMiddleware`
5. `SubAgentMiddleware` — SubAgent 委派
6. `SummarizationMiddleware`
7. `AnthropicPromptCachingMiddleware`
8. `PatchToolCallsMiddleware`
9. （可选）用户自定义 middleware
10. （可选）`HumanInTheLoopMiddleware` — 如果指定了 interrupt_on

### 现有项目文件结构

```
app/
├── deepagents/
│   ├── main_agent.py              # 主 Agent（需重构：任务 3）
│   ├── factory.py                 # Agent 工厂（需简化：任务 9）
│   ├── component_cache.py         # 组件缓存（需简化：任务 3）
│   └── subagents/
│       ├── __init__.py            # SubAgent 注册（需扩展：任务 7）
│       ├── analyze_agent.py
│       ├── data_agent.py
│       └── execute_agent.py
├── middleware/
│   ├── error_filtering_middleware.py
│   ├── logging_middleware.py
│   └── message_trimming_middleware.py  # 需删除：任务 4
├── tools/
│   ├── command_executor_tools.py   # 需修复安全漏洞：任务 10
│   ├── alert_tools.py             # 需重构：任务 11
│   ├── k8s/
│   ├── prometheus/
│   └── loki/
├── memory/
│   ├── memory_manager.py          # 需接入框架：任务 6
│   ├── sqlite_fts_store.py
│   └── sqlite_memory_store.py
├── services/
│   ├── agent_chat_service.py      # 核心入口
│   ├── enhanced_*_service.py      # 需清理：任务 9
│   ├── approval_config_service.py # 需接入 middleware：任务 2
│   └── session_state_manager.py
├── prompts/
│   ├── main_agent.py
│   └── subagents/
├── core/
│   ├── config.py                  # 需加固：任务 10
│   ├── security.py
│   └── llm_factory.py
└── main.py                        # 需修改 startup：任务 3、10

skills/                            # 需填充：任务 5（当前为空）
```
