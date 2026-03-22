# Tool Extension Guide

> 📖 For the complete guide, see: [EXTENSION_GUIDE.md](EXTENSION_GUIDE_ZH.md)

---

## 🚀 Create a New Tool in 30 Seconds

```python
from app.tools.base import BaseOpTool, register_tool, OperationType, RiskLevel

@register_tool(
    group="k8s.read",                    # Group
    operation_type=OperationType.READ,   # Type: READ/WRITE/UPDATE/DELETE
    risk_level=RiskLevel.LOW,            # Risk: LOW/MEDIUM/HIGH
    permissions=["k8s.view"],            # Permissions
    description="Get Pod list",          # Description
)
class GetPodsTool(BaseOpTool):
    async def execute(self, namespace: str = "default", **kwargs):
        # Implementation
        return {"success": True, "data": [...]}
```

✅ **That's it!** The tool is automatically registered to the system.

---

## 📋 Parameter Quick Reference

| Parameter | Values | Description |
|-----------|---------|-------------|
| `group` | `"k8s.read"` | Group code |
| `operation_type` | `READ/WRITE/UPDATE/DELETE` | Operation type |
| `risk_level` | `LOW/MEDIUM/HIGH` | HIGH requires approval |
| `permissions` | `["k8s.view"]` | Required permissions list |

---

## 🔧 Fallback Pattern (Required)

```python
async def execute(self, **kwargs):
    try:
        return await self._execute_with_sdk(**kwargs)  # SDK first
    except Exception:
        return await self.fallback.execute(...)         # CLI fallback
```

---

## 📦 Tool Locations

```
app/tools/
├── k8s/read_tools.py      # K8s read operations
├── k8s/write_tools.py     # K8s write operations
├── k8s/delete_tools.py    # K8s delete operations
├── prometheus/read_tools.py  # Prometheus query
└── loki/read_tools.py     # Loki log query
```

---

## ✅ Verify Tools

```python
from app.tools.registry import get_tool_registry

registry = get_tool_registry()
print(f"Tool count: {len(registry.list_tools())}")  # Should show 24+
```

---

## 🔐 Permission Naming Convention

```
{system}.{resource}.{operation}

k8s.view          # K8s view permission
k8s.delete_pods   # K8s delete Pod permission
prometheus.view   # Prometheus query permission
loki.view         # Loki log view permission
```

---

## 💡 Best Practices

1. **SDK → CLI Fallback**: All tools must support it
2. **Type Annotations**: Use `Optional[str]`, `Dict[str, Any]`, etc.
3. **Error Handling**: Return `{"success": False, "error": "..."}`
4. **Tool Naming**: Class `GetPodsTool`, tool name auto-extracted as `get_pods`

---

**Detailed Docs**: [EXTENSION_GUIDE.md](EXTENSION_GUIDE_ZH.md)
