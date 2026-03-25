# 记忆系统改进总结

> 基于 OpenClaw 的检索式访问设计
> 改进时间：2026-03-25 14:23 UTC

---

## ✅ 完成的改进

### 改进 1：智能检索（业务层过滤）

**文件**: `app/memory/memory_manager.py`

**新增方法**: `smart_search()`

**功能**:
- 自动分类查询意图（具体资源/故障诊断/集群概况/通用查询）
- 根据意图选择检索策略
- 自动过滤记忆

**示例**:
```python
# 自动判断查询意图
memories = await memory.smart_search(
    query="ka-baseline-tms 的 redis 版本",
    context={"namespace": "ka-baseline-tms"}
)

# 返回结果：
# - 具体资源查询 → 磴列表（不检索）
# - 故障诊断 → 检索故障记忆
# - 集群概况 → 检索知识库
# - 通用查询 → 默认策略
```

---

### 改进 2：延迟加载（Lazy Loading）

**文件**: 
- `app/services/enhanced_data_agent_service.py`
- `app/services/enhanced_analyze_service.py`

**新增方法**: `_should_use_memory()`

**功能**:
- 判断是否需要使用记忆
- 只在需要时才检索记忆
- 避免不必要的记忆检索

**示例**:
```python
def _should_use_memory(self, query: str) -> bool:
    """判断是否需要使用记忆"""
    # 具体资源查询 → 不使用记忆
    if any(kw in query for kw in ["版本", "配置", "状态", "日志"]):
        return False
    
    # 故障诊断 → 使用记忆
    if any(kw in query for kw in ["错误", "异常", "失败", "告警"]):
        return True
    
    # 默认使用记忆
    return False
```

---

### 改进 3：Token 管理

**文件**: `app/memory/memory_manager.py`

**新增方法**:
- `_estimate_tokens()` - 估算 Token 数量
- `_truncate_to_token_limit()` - 截断文本到 Token 限制

**改进方法**: `build_context()`

**功能**:
- 实时监控 Token 使用量
- 自动截断超限文本
- 添加警告日志

**示例**:
```python
# 实时监控
current_tokens = self._estimate_tokens(context)
if current_tokens > max_tokens:
    # 自动截断
    context = self._truncate_to_token_limit(context, max_tokens)
    logger.warning(f"⚠️ Token 超限，已截断")
```

---

## 📊 改进前后对比

### 改进前

```python
# ❌ 无条件检索记忆
memories = await memory.memory_search(query, ...)

# ❌ 无条件构建上下文
if memories:
    context = await memory.build_context(query)
    # 使用 context
```

### 改进后

```python
# ✅ 先判断是否需要
if self._should_use_memory(query):
    # ✅ 使用智能检索
    memories = await memory.smart_search(query, context)
    
    # ✅ 匉需构建上下文
    if memories:
        context = await memory.build_context(query, max_tokens=2000)
        # ✅ Token 监控
        current_tokens = self._estimate_tokens(context)
        if current_tokens > max_tokens:
            context = self._truncate_to_token_limit(context, max_tokens)
        # 使用 context
```

---

## 🎯 核心改进点

| 改进点 | 改进前 | 改进后 |
|--------|--------|--------|
| **检索策略** | 无条件检索 | ✅ 智能检索（按意图） |
| **加载方式** | 立即加载 | ✅ 延迟加载（lazy loading） |
| **Token 管理** | 无监控 | ✅ 实时监控 + 自动截断 |
| **业务过滤** | 无 | ✅ 按意图自动过滤 |
| **性能优化** | 浪费资源 | ✅ 按需使用 |

---

## 🔧 修改文件列表

| 文件 | 修改内容 | 状态 |
|------|---------|------|
| `app/memory/memory_manager.py` | 新增 smart_search、_estimate_tokens、_truncate_to_token_limit | ✅ |
| `app/services/enhanced_data_agent_service.py` | 新增 _should_use_memory，使用 smart_search | ✅ |
| `app/services/enhanced_analyze_service.py` | 新增 _should_use_memory、使用 smart_search | ✅ |

---

## 📝 使用示例

### 场景 1：具体资源查询（不使用记忆）

```python
# 输入
query = "ka-baseline-tms 的 redis 版本"

# 处理流程
1. _should_use_memory() → False（不使用记忆）
2. smart_search() → 返回空列表
3. 直接查询实时数据

# 输出
返回 ka-baseline-tms 的 redis 版本（不包含历史记忆）
```

---

### 场景 2：故障诊断（使用记忆）

```python
# 输入
query = "数据库连接失败怎么办？"

# 处理流程
1. _should_use_memory() → True（使用记忆）
2. smart_search() → 检索故障记忆
3. build_context() → 构建上下文（带 Token 监控）

# 输出
返回故障诊断和解决方案（包含历史相似案例）
```

---

### 场景 3：集群概况（使用知识库）

```python
# 输入
query = "集群有多少个节点？"

# 处理流程
1. _should_use_memory() → True（使用记忆）
2. smart_search() → 检索知识库（低相关性阈值）
3. build_context() → 构建上下文

# 输出
返回集群节点数量（包含知识库信息）
```

---

## ⚠️ 注意事项

### 1. 意图分类规则

可以根据实际需求调整 `_classify_intent()` 中的关键词：

```python
# 添加更多关键词
specific_keywords = ["版本", "version", "配置", "config", "状态", "status", "日志", "log", "yaml", "ip", "端口"]
diagnosis_keywords = ["错误", "error", "异常", "exception", "失败", "fail", "告警", "alert", "故障", "诊断", "排查", "慢查询", "超时"]
```

---

### 2. Token 阈值

根据模型限制调整 `max_tokens`：

```python
# 模型 Token 限制
GLM-4: 8192 tokens
GLM-4-Flash: 4096 tokens
Claude-3.5-Sonnet: 200000 tokens

# 建议配置
max_tokens = 2000  # 保守值，避免占用过多上下文
```

---

### 3. 相关性阈值

根据场景调整 `min_score`：

```python
# 具体资源查询 → 不检索
# 故障诊断 → 0.7（中等阈值）
# 集群概况 → 0.6（较低阈值）
# 通用查询 → 0.7（默认阈值）
```

---

## 🚀 下一步改进

### 短期（1 周）

- [ ] 添加记忆质量评估
- [ ] 实现记忆压缩和摘要
- [ ] 添加记忆过期清理

### 长期（2 周）

- [ ] 完全匹配 OpenClaw 的文件存储层
- [ ] 实现分层记忆（长期/短期）
- [ ] 添加 Token 主动刷新

---

## ✅ 完成清单

- [x] 新增 smart_search 方法（业务层过滤）
- [x] 新增 _should_use_memory 方法（延迟加载）
- [x] 新增 _estimate_tokens 方法（Token 估算）
- [x] 新增 _truncate_to_token_limit 方法（Token 截断）
- [x] 修改 enhanced_data_agent_service.py（使用延迟加载）
- [x] 修改 enhanced_analyze_service.py（使用延迟加载）
- [x] 改进 build_context 方法（实时 Token 监控）

---

**改进完成时间**: 2026-03-25 14:23 UTC  
**参考架构**: OpenClaw 记忆系统  
**工作量**: 约 1 小时  
**状态**: ✅ 完成
