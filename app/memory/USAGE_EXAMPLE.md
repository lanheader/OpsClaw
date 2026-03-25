# 记忆系统使用指南

## ⚠️ 重要变更（参考 OpenClaw 设计）

### 改进前（自动注入）

```python
# ❌ 旧方式：自动注入（已禁用）
class MemoryMiddleware:
    async def process_input(self, messages):
        context = await memory.build_context(user_query)
        # 自动注入，无法控制！
        enhanced_messages.insert(idx, system_msg)
        return enhanced_messages
```

### 改进后（检索式访问）

```python
# ✅ 新方式：检索式访问（参考 OpenClaw）
class DataAgent:
    async def collect_data(self, query: str):
        # 1. 按需检索记忆（不自动注入）
        memories = await memory.memory_search(
            query=query,
            max_results=3,
            min_score=0.8
        )
        
        # 2. 自主决定是否使用记忆
        if memories:
            context = memory.build_context(query)
            enhanced_query = f"{query}\n\n参考资料：\n{context}"
        else:
            enhanced_query = query
        
        # 3. 执行任务
        return await tools.invoke(enhanced_query)
```

---

## 📚 API 文档

### 1. memory_search（推荐）

**用途**：语义搜索记忆（类似 OpenClaw 的 memory_search 工具）

**参数**：
- `query`: 查询文本
- `max_results`: 最大返回数量（默认 5）
- `min_score`: 最小相似度阈值（默认 0.7）
- `include_mem0`: 是否包含 Mem0 通用对话记忆（默认 True）
- `include_incidents`: 是否包含故障记忆（默认 True）
- `include_knowledge`: 是否包含知识库（默认 True）
- `include_session`: 是否包含会话记忆（默认 False）
- `session_id`: 会话 ID（可选）

**返回**：
```python
[
    {
        "content": "记忆内容",
        "source": "mem0_user | mem0_session | incident | knowledge | session",
        "similarity": 0.85,  # 相似度（0-1）
        "metadata": {...}    # 元数据
    },
    ...
]
```

**示例**：
```python
from app.memory.memory_manager import get_memory_manager

memory = get_memory_manager()

# 1. 基础用法
memories = await memory.memory_search(
    query="ka-baseline-tms 的 redis 版本",
    max_results=5,
    min_score=0.8
)

# 2. 只检索 Mem0 通用对话记忆
memories = await memory.memory_search(
    query="用户偏好",
    include_incidents=False,
    include_knowledge=False
)

# 3. 只检索故障记忆
memories = await memory.memory_search(
    query="数据库连接失败",
    include_mem0=False,
    include_knowledge=False
)

# 4. 检索会话记忆
memories = await memory.memory_search(
    query="之前讨论过什么",
    include_session=True,
    session_id="session_123"
)
```

---

### 2. build_context（保留）

**用途**：构建格式化的上下文字符串（由调用者决定是否使用）

**参数**：
- `user_query`: 用户查询
- `session_id`: 会话 ID（可选）
- `include_incidents`: 是否包含故障记忆（默认 True）
- `include_knowledge`: 是否包含知识库（默认 True）
- `include_session`: 是否包含会话记忆（默认 False）
- `include_mem0`: 是否包含 Mem0 记忆（默认 True）
- `max_tokens`: 最大 token 数（默认 3000）

**返回**：格式化的上下文字符串

**示例**：
```python
# 1. 检索记忆
memories = await memory.memory_search(query, max_results=5)

# 2. 如果有记忆，构建上下文
if memories:
    context = await memory.build_context(
        user_query=query,
        session_id=session_id,
        max_tokens=2000
    )
    
    # 3. 增强查询（由 Subagent 决定）
    enhanced_query = f"{query}\n\n参考资料：\n{context}"
else:
    enhanced_query = query
```

---

## 🎯 最佳实践

### 1. 在 Subagent 中使用记忆

```python
# app/deepagents/subagents/data_agent.py

class DataAgent:
    """数据采集子智能体"""
    
    def __init__(self):
        self.memory = get_memory_manager()
        self.tools = {...}
    
    async def collect_data(self, query: str, namespace: str = None):
        """
        采集数据（带记忆增强）
        
        Args:
            query: 用户查询
            namespace: 命名空间（可选）
        """
        
        # 1. 检索相关记忆
        memories = await self.memory.memory_search(
            query=query,
            max_results=3,
            min_score=0.8,  # 高相关性阈值
            include_mem0=False,  # 不包含通用对话记忆
            include_incidents=True,
            include_knowledge=True
        )
        
        # 2. 过滤记忆（Subagent 自主决策）
        if namespace:
            # 只保留匹配命名空间的记忆
            memories = [
                m for m in memories
                if m.get("metadata", {}).get("namespace") == namespace
            ]
        
        # 3. 构建上下文（如果需要）
        if memories:
            context = await self.memory.build_context(
                user_query=query,
                include_mem0=False,
                max_tokens=2000
            )
            
            # ⚠️ 添加明确指导（参考 OpenClaw）
            enhanced_query = f"""{query}

参考资料（来自历史记录和知识库）：
{context}

⚠️ 重要规则：
1. 如果参考资料与用户问题**不匹配**，请**忽略**它
2. 直接回答用户的具体问题，不要回答通用信息
3. 如果不知道答案，就说"我需要查询实时数据"
"""
        else:
            enhanced_query = query
        
        # 4. 执行采集
        result = await self.tools["get_pods"].ainvoke(enhanced_query)
        
        # 5. 存储记忆（可选）
        if namespace:
            await self.memory.remember_message(
                session_id="data_collection",
                role="assistant",
                content=f"查询 {namespace} 的数据: {result[:200]}",
                importance=0.7
            )
        
        return result
```

---

### 2. 不同场景的检索策略

```python
# 场景 1：具体资源查询（高相关性）
memories = await memory.memory_search(
    query="ka-baseline-tms 的 redis 版本",
    max_results=3,
    min_score=0.9,  # 高阈值
    include_mem0=False,
    include_incidents=False,
    include_knowledge=False
)

# 场景 2：故障诊断（中等相关性）
memories = await memory.memory_search(
    query="数据库连接失败",
    max_results=5,
    min_score=0.7,
    include_mem0=True,
    include_incidents=True,
    include_knowledge=True
)

# 场景 3：集群概况（低相关性）
memories = await memory.memory_search(
    query="集群概况",
    max_results=10,
    min_score=0.6,  # 低阈值
    include_mem0=False,
    include_incidents=False,
    include_knowledge=True
)

# 场景 4：会话上下文（会话记忆）
memories = await memory.memory_search(
    query="之前讨论过什么",
    max_results=5,
    min_score=0.7,
    include_mem0=True,
    include_session=True,
    session_id=session_id
)
```

---

## 🔧 配置

### 环境变量

```bash
# .env

# Mem0 配置
MEM0_ENABLED=true
MEM0_PROVIDER=openai  # 可选：openai, ollama, claude, zhipu
MEM0_MODEL=gpt-4o-mini  # 可选
MEM0_AUTO_LEARN=true  # 自动学习

# ChromaDB 配置（自动使用）
USE_CHROMADB=true
```

---

## 📊 对比 OpenClaw

| 特性 | OpenClaw | OpsClaw（改进后） |
|------|---------|-----------------|
| **通用对话记忆** | MEMORY.md | ✅ Mem0 |
| **短期记忆** | memory/*.md | ✅ ChromaDB |
| **检索方式** | memory_search | ✅ memory_search |
| **自动注入** | ❌ 不自动注入 | ✅ 不自动注入 |
| **分层设计** | 文件 + LanceDB | ✅ Mem0 + ChromaDB |

---

## ⚠️ 注意事项

1. **不要自动注入**：参考 OpenClaw，记忆应该按需检索，不自动注入
2. **Subagent 自主决策**：由 Subagent 决定是否使用记忆、如何使用
3. **相关性阈值**：根据场景调整 `min_score`（0.6-0.9）
4. **Token 管理**：注意 `max_tokens` 限制，避免上下文过长
5. **安全隔离**：群聊场景不应该加载用户的长期记忆

---

## 🎯 迁移指南

### 从旧方式迁移

```python
# ❌ 旧方式（自动注入）
# 不需要修改代码，中间件已经禁用自动注入

# ✅ 新方式（检索式访问）
# 在 Subagent 中添加记忆检索逻辑

class MySubagent:
    async def handle_query(self, query: str):
        # 1. 检索记忆
        memories = await memory.memory_search(query, max_results=3)
        
        # 2. 自主决策
        if memories:
            context = await memory.build_context(query)
            enhanced_query = f"{query}\n\n{context}"
        else:
            enhanced_query = query
        
        # 3. 执行任务
        return await self.execute(enhanced_query)
```

---

## 📚 参考资料

- [OpenClaw 记忆系统设计](https://docs.openclaw.ai/memory)
- [Mem0 官方文档](https://docs.mem0.ai)
- [ChromaDB 官方文档](https://docs.trychroma.com)
