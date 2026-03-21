# 工具扩展快速参考

> 📖 完整指南请参考：[EXTENSION_GUIDE.md](./EXTENSION_GUIDE.md)

---

## 🚀 30 秒创建新工具

```python
from app.tools.base import BaseOpTool, register_tool, OperationType, RiskLevel

@register_tool(
    group="k8s.read",                    # 分组
    operation_type=OperationType.READ,   # 类型: READ/WRITE/UPDATE/DELETE
    risk_level=RiskLevel.LOW,            # 风险: LOW/MEDIUM/HIGH
    permissions=["k8s.view"],            # 权限
    description="获取 Pod 列表",          # 描述
)
class GetPodsTool(BaseOpTool):
    async def execute(self, namespace: str = "default", **kwargs):
        # 实现逻辑
        return {"success": True, "data": [...]}
```

✅ **就这么简单！** 工具会自动注册到系统。

---

## 📋 参数速查表

| 参数 | 值 | 说明 |
|------|-----|------|
| `group` | `"k8s.read"` | 分组代码 |
| `operation_type` | `READ/WRITE/UPDATE/DELETE` | 操作类型 |
| `risk_level` | `LOW/MEDIUM/HIGH` | HIGH 需要批准 |
| `permissions` | `["k8s.view"]` | 所需权限列表 |

---

## 🔧 降级模式（必须）

```python
async def execute(self, **kwargs):
    try:
        return await self._execute_with_sdk(**kwargs)  # SDK 优先
    except Exception:
        return await self.fallback.execute(...)         # CLI 降级
```

---

## 📦 工具位置

```
app/tools/
├── k8s/read_tools.py      # K8s 读操作
├── k8s/write_tools.py     # K8s 写操作
├── k8s/delete_tools.py    # K8s 删除操作
├── prometheus/read_tools.py  # Prometheus 查询
└── loki/read_tools.py     # Loki 日志查询
```

---

## ✅ 验证工具

```python
from app.tools.registry import get_tool_registry

registry = get_tool_registry()
print(f"工具数: {len(registry.list_tools())}")  # 应显示 24+
```

---

## 🔐 权限命名规范

```
{系统}.{资源}.{操作}

k8s.view          # K8s 查看权限
k8s.delete_pods   # K8s 删除 Pod 权限
prometheus.view   # Prometheus 查询权限
loki.view         # Loki 日志查看权限
```

---

## 💡 最佳实践

1. **SDK → CLI 降级**：所有工具必须支持
2. **类型注解**：使用 `Optional[str]`、`Dict[str, Any]` 等
3. **错误处理**：返回 `{"success": False, "error": "..."}`
4. **工具命名**：类名 `GetPodsTool`，工具名自动提取为 `get_pods`

---

**详细文档**: [EXTENSION_GUIDE.md](./EXTENSION_GUIDE.md)
