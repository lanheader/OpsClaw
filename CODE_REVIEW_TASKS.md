# OpsClaw 代码审查报告 - 改进任务清单

> 审查时间：2026-03-31
> 分支：develop（c4b3baf）
> 代码总量：29,739 行（app/ 目录）

---

## 🔴 高优先级（必须修）

### 任务 A：DynamicPermissionMiddleware 真正接入 Agent 图

**问题**：middleware 文件写好了（208行），但 `create_base_agent()` 只注入了 `ErrorFilteringMiddleware` + `LoggingMiddleware`，权限/审批 middleware 没挂上去。`DynamicAgentWrapper` 的 docstring 说"已通过 middleware 注入"，实际并没有。

**文件**：
- `app/deepagents/main_agent.py` — `create_base_agent()` 函数
- `app/middleware/dynamic_permission_middleware.py` — 已实现，未接入
- `app/middleware/dynamic_approval_middleware.py` — 已实现，未接入

**要求**：
1. 研究 deepagents v0.4.12 的 `create_deep_agent()` 的 `middleware` 参数如何传递每次请求不同的 middleware 实例
2. 如果框架不支持运行时动态注入 middleware，则修改 `DynamicAgentWrapper` 在 `ainvoke`/`astream` 前手动将权限/审批 middleware 注入到 base_agent 的中间件栈中
3. 确保每次请求创建新的 middleware 实例（携带当前用户的权限和 user_id）
4. 写一个测试验证权限拦截确实生效

---

### 任务 B：Loki 工具接入真实 SDK

**问题**：`app/tools/loki/read_tools.py` 三个工具函数全部返回空数据 `logs: []`，有 3 个 `TODO: 实现真实的 Loki SDK 调用`。`app/integrations/loki/client.py` 已有客户端实现，但 Loki 工具根本没调用它。

**文件**：
- `app/tools/loki/read_tools.py` — 3 个 TODO 空壳工具
- `app/integrations/loki/client.py` — 已有客户端，需确认是否可用

**要求**：
1. 检查 `app/integrations/loki/client.py` 的实现是否完整可用
2. 如果可用，在 `read_tools.py` 中调用该客户端替换空壳实现
3. 如果不可用，基于 httpx 实现 Loki LogQL 查询（`GET /loki/api/v1/query_range`）
4. 保留现有的 tool_success_response 格式，只替换数据来源

---

### 任务 C：Alert 诊断接口加认证

**问题**：`GET /api/v2/alert/{task_id}/diagnosis` 没有挂认证中间件，任何人都可以查询告警诊断报告（可能包含集群敏感信息）。

**文件**：`app/api/v2/alert.py`

**要求**：
1. 给 `get_diagnosis` 接口加上认证（参考 `app/api/v2/chat.py` 的认证方式）
2. Webhook 接口 `POST /api/v2/alert/webhook` 保持无需认证（监控系统集成需要）
3. 确保 401 响应格式与项目其他接口一致

---

### 任务 D：修复 scheduler_service 的 bare except

**问题**：`app/services/scheduler_service.py` 第 241 行和第 342 行有 `except: pass`，会吞掉所有异常，定时任务失败时完全静默。

**文件**：`app/services/scheduler_service.py`

**要求**：
1. 将 `except:` 改为 `except Exception as e:`，并记录日志
2. 第 241 行：定时任务执行失败时应记录完整异常信息，包含 task_id
3. 第 342 行：查询下次执行时间失败时应记录异常并返回合理的默认值

---

## 🟡 中优先级（建议修）

### 任务 E：删除死代码 vector_helpers.py

**问题**：`app/utils/vector_helpers.py` 371 行，使用 numpy，全项目无任何引用。项目已明确不使用 embedding。

**文件**：`app/utils/vector_helpers.py`

**要求**：
1. 删除 `app/utils/vector_helpers.py`
2. 全局搜索确认无引用
3. 从 `pyproject.toml` 的 dependencies 中移除 `chromadb>=0.4.0`（向量数据库依赖，项目已改用 SQLite FTS5）
4. 清理 `app/utils/loguru_config.py` 中 `chromadb: INFO` 的日志配置

---

### 任务 F：删除死代码 debug_logger.py

**问题**：`app/utils/debug_logger.py` 371 行，全项目无任何引用。

**文件**：`app/utils/debug_logger.py`

**要求**：
1. 全局搜索确认无引用
2. 删除文件

---

### 任务 G：统一记忆注入路径

**问题**：存在两条重复的记忆注入路径：
- 路径 A：`agent_chat_service._inject_memory()` → 手动把记忆拼接到用户消息前面
- 路径 B：`main_agent._generate_dynamic_memory()` → MemoryMiddleware 加载 AGENTS.md

两条路径同时存在可能导致重复注入。

**文件**：
- `app/services/agent_chat_service.py` — `_inject_memory()` 函数
- `app/deepagents/main_agent.py` — `_generate_dynamic_memory()` + `create_base_agent()` 的 `memory` 参数

**要求**：
1. 评估两条路径是否真的会同时触发
2. 如果是，选择保留一条：
   - 推荐保留路径 A（`_inject_memory`），因为它支持按用户查询、会话摘要等丰富功能
   - 路径 B 的 `_generate_dynamic_memory` 只生成了简单的集群信息
3. 清理被废弃的路径

---

### 任务 H：k8s/read_tools.py 拆分

**问题**：单个文件 1294 行，包含所有 K8s 读操作工具，维护困难。

**文件**：`app/tools/k8s/read_tools.py`

**要求**：
1. 按资源类型拆分为多个文件，建议结构：
   - `app/tools/k8s/read_pod_tools.py` — Pod 相关查询
   - `app/tools/k8s/read_workload_tools.py` — Deployment/StatefulSet/DaemonSet
   - `app/tools/k8s/read_service_tools.py` — Service/Ingress/NetworkPolicy
   - `app/tools/k8s/read_resource_tools.py` — Node/PVC/ConfigMap/Secret 等
2. 共享的 `_init_k8s_client()`、`_log_tool_start()` 等辅助函数放到 `app/tools/k8s/common.py`
3. 确保拆分后所有工具仍然通过 `app/tools/k8s/__init__.py` 正确导出
4. 不要修改工具的外部接口（名称、参数、返回格式），只拆文件

---

### 任务 I：飞书 client 清理 print 残留

**问题**：两处 `print()` 调试语句。

**文件**：
- `app/integrations/feishu/client.py:377` — `print(f"User name: {user_info.get('name')}")`
- `app/integrations/feishu/lark_longconn.py:304` — `print("\n正在停止...")`

**要求**：
1. 替换为 `logger.info()` 或 `logger.debug()`
2. 使用已有的 `from app.utils.logger import get_logger`

---

## 🟢 低优先级（有空再修）

### 任务 J：SubAgent prompt 加载失败降级

**问题**：`_load_prompt()` 从数据库加载 prompt，数据库没有 `agent_prompts` 表时直接抛 `ValueError`。生产环境第一次启动如果没初始化数据库，Agent 无法创建。

**文件**：`app/deepagents/subagents/__init__.py` — `_load_prompt()` 函数

**要求**：
1. 当数据库查询失败或 prompt 不存在时，从静态文件降级加载（`app/prompts/subagents/data.py` 等文件已存在）
2. 加载失败时使用默认 prompt（至少包含角色描述），而不是抛异常
3. 记录警告日志

---

### 任务 K：清理 component_cache.py 和 main_agent.py 的缓存重叠

**问题**：`ComponentCache` 缓存了 subagents、middleware、tools，但 `main_agent.py` 的 `_cached_base_agent` 缓存了整个 Agent 图。两者并存容易混乱。

**文件**：
- `app/deepagents/component_cache.py`
- `app/deepagents/main_agent.py`

**要求**：
1. 评估两个缓存是否真的有重叠
2. 如果有，统一为一个缓存层
3. 确保缓存失效逻辑一致

---

## 📋 执行建议

1. **先修高优先级**（任务 A-D），这些影响功能正确性和安全性
2. **再修中优先级**（任务 E-I），这些是代码质量和可维护性
3. **低优先级**（任务 J-K）可以排到下个迭代
4. **每个任务完成后单独 git commit**
5. **代码注释用中文**
6. **遇到不确定的决策点先标注 TODO 继续推进，不卡住**

## ⚠️ 约束

- 所有改动必须基于 deepagents v0.4.12 框架的实际 API
- 不要引入新的外部模型依赖（不使用 embedding 模型）
- 不要修改已有工具的外部接口（名称、参数、返回格式）
