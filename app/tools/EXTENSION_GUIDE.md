# Tool Extension Guide

This guide explains how to extend the Ops Agent tool system, including adding new tools, creating tool groups, and configuring permissions.

---

## 📁 Directory Structure

```
app/tools/
├── __init__.py              # Tool exports and utility functions
├── base.py                  # BaseOpTool base class and decorator
├── registry.py              # ToolRegistry tool registry
├── fallback.py              # CLI fallback mechanism
│
├── k8s/                     # K8s tool group
│   ├── __init__.py
│   ├── read_tools.py        # Read operation tools
│   ├── write_tools.py       # Write operation tools
│   └── delete_tools.py      # Delete operation tools
│
├── prometheus/              # Prometheus tool group
│   ├── __init__.py
│   └── read_tools.py        # Query tools
│
└── loki/                    # Loki tool group
    ├── __init__.py
    └── read_tools.py        # Log query tools
```

---

## 🚀 Quick Start: Add a New Tool

### Step 1: Create Tool File

Create a tool file in the corresponding group directory, e.g., `app/tools/k8s/read_tools.py`:

```python
"""
K8s Read Operation Tools
"""

from typing import Dict, Any, Optional
import logging

from app.tools.base import (
    BaseOpTool,
    register_tool,
    OperationType,
    RiskLevel,
)
from app.tools.fallback import get_k8s_fallback

logger = logging.getLogger(__name__)


@register_tool(
    group="k8s.read",                    # Tool group code
    operation_type=OperationType.READ,   # Operation type
    risk_level=RiskLevel.LOW,            # Risk level
    permissions=["k8s.view"],            # Required permissions
    description="Get Pod list",           # Tool description
    examples=[                           # Usage examples
        "get_pods(namespace='default')",
        "get_pods(namespace='production', label_selector='app=api')",
    ],
)
class GetPodsTool(BaseOpTool):
    """
    Get Pod List Tool

    Query all Pods in a specified namespace via SDK or kubectl.
    """

    def __init__(self):
        from app.integrations.kubernetes.client import K8sClient
        self.k8s_client = K8sClient()
        self.fallback = get_k8s_fallback()

    async def execute(
        self,
        namespace: str = "default",
        label_selector: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute tool operation

        Args:
            namespace: Namespace
            label_selector: Label selector

        Returns:
            Operation result dictionary
        """
        try:
            # Prefer SDK
            logger.info(f"Using K8s SDK to list pods in {namespace}")
            result = await self._execute_with_sdk(namespace, label_selector)
            return result
        except Exception as e:
            # SDK failed, fallback to CLI
            logger.warning(f"K8s SDK failed: {e}, falling back to CLI")
            result = await self.fallback.execute(
                operation="get pods",
                namespace=namespace,
                label_selector=label_selector
            )
            return result

    async def _execute_with_sdk(
        self,
        namespace: str,
        label_selector: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute using SDK"""
        pods = await self.k8s_client.list_namespaced_pod(
            namespace=namespace,
            label_selector=label_selector
        )

        data = [
            {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "phase": pod.status.phase,
                "ready": self._is_pod_ready(pod),
            }
            for pod in pods.items
        ]

        return {
            "success": True,
            "data": data,
            "execution_mode": "sdk",
            "source": "kubernetes-sdk",
        }

    def _is_pod_ready(self, pod) -> bool:
        """Check if Pod is ready"""
        if not pod.status.container_statuses:
            return False
        return all(cs.ready for cs in pod.status.container_statuses)
```

### Step 2: Tool Auto-Registration

Using the `@register_tool` decorator, tools are **automatically registered** to `ToolRegistry` - no manual configuration needed!

### Step 3: Verify Tool

```python
# Verify tool is registered successfully
from app.tools.registry import get_tool_registry

registry = get_tool_registry()
print(f"Tool count: {len(registry.list_tools())}")

# Get specific tool
tool_class = registry.get_tool("get_pods")
print(f"Tool name: {tool_class.get_metadata().name}")
```

---

## 🔧 Tool Configuration Parameters

### @register_tool Decorator Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `group` | str | ✅ | Tool group code, e.g., `"k8s.read"` |
| `operation_type` | OperationType | ✅ | Operation type: READ/WRITE/UPDATE/DELETE |
| `risk_level` | RiskLevel | ✅ | Risk level: LOW/MEDIUM/HIGH |
| `permissions` | List[str] | ✅ | Required permissions list, e.g., `["k8s.view"]` |
| `description` | str | ✅ | Tool description for AI to understand tool functionality |
| `examples` | List[str] | ❌ | Usage examples to help AI understand how to call |

### RiskLevel

| Level | Description | Example |
|-------|-------------|---------|
| `RiskLevel.LOW` | Read-only operations, no side effects | `get_pods`, `get_logs` |
| `RiskLevel.MEDIUM` | Modify operations, may affect service | `scale_deployment` |
| `RiskLevel.HIGH` | Destructive operations, requires approval | `delete_pod`, `restart_deployment` |

### OperationType

| Type | Description |
|------|-------------|
| `OperationType.READ` | Query operations |
| `OperationType.WRITE` | Create/update operations |
| `OperationType.UPDATE` | Modify operations |
| `OperationType.DELETE` | Delete operations |

---

## 📦 Create New Tool Group

### Step 1: Define Tool Group

Add new group in `ToolRegistry._init_groups()` in `app/tools/registry.py`:

```python
# Add in _init_groups method
ToolGroup(
    code="custom.query",
    name="Custom Query",
    category=ToolCategory.CUSTOM,  # Need to add in ToolCategory
    operation_type=OperationType.READ,
    description="Custom system query operations"
),
```

### Step 2: Create Tool Directory

```bash
mkdir -p app/tools/custom
touch app/tools/custom/__init__.py
```

### Step 3: Implement Tool

```python
# app/tools/custom/query_tools.py

from app.tools.base import (
    BaseOpTool,
    register_tool,
    OperationType,
    RiskLevel,
)

@register_tool(
    group="custom.query",
    operation_type=OperationType.READ,
    risk_level=RiskLevel.LOW,
    permissions=["custom.view"],
    description="Query custom data",
)
class QueryCustomDataTool(BaseOpTool):
    async def execute(self, **kwargs) -> Dict[str, Any]:
        # Implement query logic
        return {
            "success": True,
            "data": {...},
        }
```

---

## 🛡️ CLI Fallback Mechanism

All tools **must** support SDK → CLI fallback!

### Implement Fallback

```python
from app.tools.fallback import get_k8s_fallback

class MyTool(BaseOpTool):
    def __init__(self):
        self.fallback = get_k8s_fallback()

    async def execute(self, **kwargs):
        try:
            # 1. Prefer SDK
            return await self._execute_with_sdk(**kwargs)
        except Exception as e:
            logger.warning(f"SDK failed: {e}, falling back to CLI")
            # 2. Fallback to CLI
            return await self.fallback.execute(
                operation="kubectl get pods",
                **kwargs
            )
```

### Custom FallbackExecutor

To add a new fallback executor, implement in `app/tools/fallback.py`:

```python
class CustomFallback(FallbackExecutor):
    """Custom system fallback executor"""

    async def execute(self, operation: str, **kwargs) -> Dict[str, Any]:
        cmd = self._build_command(operation, **kwargs)
        return await self._execute_command(cmd)

def get_custom_fallback() -> CustomFallback:
    return CustomFallback(
        cli_command="custom-cli",
        timeout_seconds=30,
    )
```

---

## 🔐 Permission System

### Permission Naming Convention

```
{system}.{resource}.{operation}

Examples:
- k8s.pods.view    # K8s Pod view permission
- k8s.deployments.delete  # K8s Deployment delete permission
- prometheus.metrics.query  # Prometheus query permission
- loki.logs.view   # Loki log view permission
```

### Permission Filtering

```python
from app.tools import get_all_tools

# Get tools user has permission for
tools = get_all_tools(
    permissions={"k8s.view", "prometheus.view"},
    user_id=1,
    db=db_session
)
```

### High-Risk Tool Auto-Approval

`RiskLevel.HIGH` tools automatically trigger user approval flow:

```python
from app.tools.registry import get_tool_registry, RiskLevel

registry = get_tool_registry()
high_risk_tools = [
    t.get_metadata().name
    for t in registry.list_tools()
    if t.get_metadata().risk_level == RiskLevel.HIGH
]
# Auto-includes: delete_pod, delete_deployment, restart_deployment, etc.
```

---

## 📊 Tool Status Query

### Query All Tools

```python
from app.tools.registry import get_tool_registry

registry = get_tool_registry()

# All tool classes
tools = registry.list_tools()

# All groups
groups = registry.list_groups()

# All permissions
permissions = registry.get_permissions()
```

### Query by Group

```python
from app.tools import get_tools_by_group

# Get K8s read operation tools
tools = get_tools_by_group("k8s.read")
```

### Query by Permission

```python
from app.tools import get_all_tools

# Get tools with k8s.view permission
tools = get_all_tools(permissions={"k8s.view"})
```

---

## ✅ Best Practices

### 1. Tool Naming

- Class name: Use `PascalCase` + `Tool` suffix, e.g., `GetPodsTool`
- Tool name: Use `snake_case`, decorator auto-extracts from class name, e.g., `get_pods`

### 2. Error Handling

```python
async def execute(self, **kwargs):
    try:
        # SDK logic
        result = await self._execute_with_sdk(**kwargs)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        return {"success": False, "error": str(e)}
```

### 3. Type Annotations

```python
async def execute(
    self,
    namespace: str,
    label_selector: Optional[str] = None,
    **kwargs  # Accept extra parameters
) -> Dict[str, Any]:  # Explicit return type
    ...
```

### 4. Docstrings

```python
class GetPodsTool(BaseOpTool):
    """
    Get Pod List Tool

    Features:
    - Query all Pods in specified namespace
    - Support label filtering
    - Return Pod status information

    Fallback: Use kubectl when SDK fails
    """
```

---

## 🧪 Testing Tools

### Unit Tests

```python
import pytest
from app.tools.k8s.read_tools import GetPodsTool

@pytest.mark.asyncio
async def test_get_pods_tool():
    tool = GetPodsTool()

    # Mock SDK client
    tool.k8s_client = MockK8sClient()

    result = await tool.execute(namespace="default")

    assert result["success"] is True
    assert len(result["data"]) > 0
    assert result["execution_mode"] == "sdk"
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_tool_registry():
    from app.tools.registry import get_tool_registry

    registry = get_tool_registry()
    tool_class = registry.get_tool("get_pods")

    assert tool_class is not None
    assert tool_class.get_metadata().name == "get_pods"
```

---

## 🔌 API Permission Management

### Note: API Permissions are Hardcoded

Unlike tool permissions, API permissions are managed using **hardcoded method**.

**Reasons**:
- API permissions are relatively stable and don't change frequently
- Hardcoding is simpler and more direct
- Just add permissions manually when creating new APIs

### Steps to Add API Permission

Add in `API_PERMISSIONS` list in `app/core/permissions.py`:

```python
# app/core/permissions.py

API_PERMISSIONS = [
    # ... existing permissions ...

    # New API permission
    PermissionDef(
        code="api:reports:generate",
        name="Generate Report API",
        category=PermissionCategory.API,
        resource="api:reports:generate",
        description="Allow calling report generation API",
    ),
]
```

### API Permission Code Convention

```
api:{resource}:{operation}

Examples:
- api:workflow:execute  # Execute workflow
- api:workflow:resume   # Resume workflow
- api:users:read        # Read users
- api:users:write       # Write users
```

### Sync Permissions to Database

```bash
# Sync tool permissions to database (API permissions already defined in code)
curl -X POST http://localhost:8000/api/v1/permissions/sync-tool-permissions \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Note**: API permissions don't need syncing, they're read directly from `app/core/permissions.py`.

---

## 📚 Related Documentation

- [base.py](./base.py) - Tool base class and decorator implementation
- [registry.py](./registry.py) - Tool registry implementation
- [fallback.py](./fallback.py) - CLI fallback mechanism implementation
- [k8s/read_tools.py](./k8s/read_tools.py) - K8s tool examples
- [../core/permissions.py](../core/permissions.py) - Permission definitions (including API permissions)

---

**Last Updated**: 2026-03-22
**Version**: Ops Agent v3.0+
