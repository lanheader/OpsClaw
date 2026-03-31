# 工具扩展使用说明

本指南说明如何扩展 OpsClaw 工具系统，包括新增工具、创建工具分组和配置权限。

---

## 📁 目录结构

```
app/tools/
├── __init__.py              # 工具导出和便捷函数
├── base.py                  # BaseOpTool 基类和装饰器
├── registry.py              # ToolRegistry 工具注册表
├── fallback.py              # CLI 降级机制
│
├── k8s/                     # K8s 工具组
│   ├── __init__.py
│   ├── read_tools.py        # 读操作工具
│   ├── write_tools.py       # 写操作工具
│   └── delete_tools.py      # 删除操作工具
│
├── prometheus/              # Prometheus 工具组
│   ├── __init__.py
│   └── read_tools.py        # 查询工具
│
└── loki/                    # Loki 工具组
    ├── __init__.py
    └── read_tools.py        # 日志查询工具
```

---

## 🚀 快速开始：新增一个工具

### 步骤 1：创建工具文件

在对应分组目录下创建工具文件，例如 `app/tools/k8s/read_tools.py`：

```python
"""
K8s 读操作工具
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
    group="k8s.read",                    # 工具分组代码
    operation_type=OperationType.READ,   # 操作类型
    risk_level=RiskLevel.LOW,            # 风险等级
    permissions=["k8s.view"],            # 所需权限
    description="获取 Pod 列表",          # 工具描述
    examples=[                           # 使用示例
        "get_pods(namespace='default')",
        "get_pods(namespace='production', label_selector='app=api')",
    ],
)
class GetPodsTool(BaseOpTool):
    """
    获取 Pod 列表工具

    通过 SDK 或 kubectl 查询指定命名空间下的所有 Pod。
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
        执行工具操作

        Args:
            namespace: 命名空间
            label_selector: 标签选择器

        Returns:
            操作结果字典
        """
        try:
            # 优先使用 SDK
            logger.info(f"Using K8s SDK to list pods in {namespace}")
            result = await self._execute_with_sdk(namespace, label_selector)
            return result
        except Exception as e:
            # SDK 失败，降级到 CLI
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
        """使用 SDK 执行"""
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
        """检查 Pod 是否就绪"""
        if not pod.status.container_statuses:
            return False
        return all(cs.ready for cs in pod.status.container_statuses)
```

### 步骤 2：工具自动注册

使用 `@register_tool` 装饰器后，工具会**自动注册**到 `ToolRegistry`，无需手动配置！

### 步骤 3：验证工具

```python
# 验证工具是否注册成功
from app.tools.registry import get_tool_registry

registry = get_tool_registry()
print(f"工具数量: {len(registry.list_tools())}")

# 获取特定工具
tool_class = registry.get_tool("get_pods")
print(f"工具名称: {tool_class.get_metadata().name}")
```

---

## 🔧 工具配置参数

### @register_tool 装饰器参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `group` | str | ✅ | 工具分组代码，如 `"k8s.read"` |
| `operation_type` | OperationType | ✅ | 操作类型：READ/WRITE/UPDATE/DELETE |
| `risk_level` | RiskLevel | ✅ | 风险等级：LOW/MEDIUM/HIGH |
| `permissions` | List[str] | ✅ | 所需权限列表，如 `["k8s.view"]` |
| `description` | str | ✅ | 工具描述，用于 AI 理解工具功能 |
| `examples` | List[str] | ❌ | 使用示例，帮助 AI 理解如何调用 |

### RiskLevel（风险等级）

| 等级 | 说明 | 示例 |
|------|------|------|
| `RiskLevel.LOW` | 只读操作，无副作用 | `get_pods`, `get_logs` |
| `RiskLevel.MEDIUM` | 修改操作，可能影响服务 | `scale_deployment` |
| `RiskLevel.HIGH` | 破坏性操作，需要批准 | `delete_pod`, `restart_deployment` |

### OperationType（操作类型）

| 类型 | 说明 |
|------|------|
| `OperationType.READ` | 查询操作 |
| `OperationType.WRITE` | 创建/更新操作 |
| `OperationType.UPDATE` | 修改操作 |
| `OperationType.DELETE` | 删除操作 |

---

## 📦 创建新的工具分组

### 步骤 1：定义工具分组

在 `app/tools/registry.py` 中的 `ToolRegistry._init_groups()` 添加新分组：

```python
# 在 _init_groups 方法中添加
ToolGroup(
    code="custom.query",
    name="自定义查询",
    category=ToolCategory.CUSTOM,  # 需要在 ToolCategory 中添加
    operation_type=OperationType.READ,
    description="自定义系统查询操作"
),
```

### 步骤 2：创建工具目录

```bash
mkdir -p app/tools/custom
touch app/tools/custom/__init__.py
```

### 步骤 3：实现工具

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
    description="查询自定义数据",
)
class QueryCustomDataTool(BaseOpTool):
    async def execute(self, **kwargs) -> Dict[str, Any]:
        # 实现查询逻辑
        return {
            "success": True,
            "data": {...},
        }
```

---

## 🛡️ CLI 降级机制

所有工具**必须**支持 SDK → CLI 降级！

### 实现降级

```python
from app.tools.fallback import get_k8s_fallback

class MyTool(BaseOpTool):
    def __init__(self):
        self.fallback = get_k8s_fallback()

    async def execute(self, **kwargs):
        try:
            # 1. 优先使用 SDK
            return await self._execute_with_sdk(**kwargs)
        except Exception as e:
            logger.warning(f"SDK failed: {e}, falling back to CLI")
            # 2. 降级到 CLI
            return await self.fallback.execute(
                operation="kubectl get pods",
                **kwargs
            )
```

### 自定义 FallbackExecutor

如需添加新的降级执行器，在 `app/tools/fallback.py` 中实现：

```python
class CustomFallback(FallbackExecutor):
    """自定义系统降级执行器"""

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

## 🔐 权限系统

### 权限命名规范

```
{系统}.{资源}.{操作}

示例：
- k8s.pods.view    # K8s Pod 查看权限
- k8s.deployments.delete  # K8s Deployment 删除权限
- prometheus.metrics.query  # Prometheus 查询权限
- loki.logs.view   # Loki 日志查看权限
```

### 权限过滤

```python
from app.tools import get_all_tools

# 获取用户有权限的工具
tools = get_all_tools(
    permissions={"k8s.view", "prometheus.view"},
    user_id=1,
    db=db_session
)
```

### 高风险工具自动批准

`RiskLevel.HIGH` 的工具会自动触发用户批准流程：

```python
from app.tools.registry import get_tool_registry, RiskLevel

registry = get_tool_registry()
high_risk_tools = [
    t.get_metadata().name
    for t in registry.list_tools()
    if t.get_metadata().risk_level == RiskLevel.HIGH
]
# 自动包含：delete_pod, delete_deployment, restart_deployment 等
```

---

## 📊 工具状态查询

### 查询所有工具

```python
from app.tools.registry import get_tool_registry

registry = get_tool_registry()

# 所有工具类
tools = registry.list_tools()

# 所有分组
groups = registry.list_groups()

# 所有权限
permissions = registry.get_permissions()
```

### 按分组查询

```python
from app.tools import get_tools_by_group

# 获取 K8s 读操作工具
tools = get_tools_by_group("k8s.read")
```

### 按权限查询

```python
from app.tools import get_all_tools

# 获取有 k8s.view 权限的工具
tools = get_all_tools(permissions={"k8s.view"})
```

---

## ✅ 最佳实践

### 1. 工具命名

- 类名：使用 `PascalCase` + `Tool` 后缀，如 `GetPodsTool`
- 工具名：使用 `snake_case`，装饰器会自动从类名提取，如 `get_pods`

### 2. 错误处理

```python
async def execute(self, **kwargs):
    try:
        # SDK 逻辑
        result = await self._execute_with_sdk(**kwargs)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        return {"success": False, "error": str(e)}
```

### 3. 类型注解

```python
async def execute(
    self,
    namespace: str,
    label_selector: Optional[str] = None,
    **kwargs  # 接收额外参数
) -> Dict[str, Any]:  # 明确返回类型
    ...
```

### 4. 文档字符串

```python
class GetPodsTool(BaseOpTool):
    """
    获取 Pod 列表工具

    功能：
    - 查询指定命名空间下的所有 Pod
    - 支持标签过滤
    - 返回 Pod 状态信息

    降级：SDK 失败时使用 kubectl
    """
```

---

## 🧪 测试工具

### 单元测试

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

### 集成测试

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

## 🔌 API 权限管理

### 注意：API 权限为硬编码

与工具权限不同，API 权限采用**硬编码方式**管理。

**原因**：
- API 权限相对稳定，不会频繁变更
- 硬编码更简单、更直接
- 新增 API 时手动添加权限即可

### 新增 API 权限步骤

在 `app/core/permissions.py` 的 `API_PERMISSIONS` 列表中添加：

```python
# app/core/permissions.py

API_PERMISSIONS = [
    # ... 现有权限 ...

    # 新增的 API 权限
    PermissionDef(
        code="api:reports:generate",
        name="生成报告API",
        category=PermissionCategory.API,
        resource="api:reports:generate",
        description="允许调用报告生成API",
    ),
]
```

### API 权限代码规范

```
api:{资源}:{操作}

示例：
- api:workflow:execute  # 执行工作流
- api:workflow:resume   # 恢复工作流
- api:users:read        # 读取用户
- api:users:write       # 写入用户
```

### 同步权限到数据库

```bash
# 同步工具权限到数据库（API 权限已在代码中定义）
curl -X POST http://localhost:8000/api/v1/permissions/sync-tool-permissions \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**注意**：API 权限不需要同步，它们直接从 `app/core/permissions.py` 读取。

---

## 📚 相关文档

- [base.py](./base.py) - 工具基类和装饰器实现
- [registry.py](./registry.py) - 工具注册表实现
- [fallback.py](./fallback.py) - CLI 降级机制实现
- [k8s/read_tools.py](./k8s/read_tools.py) - K8s 工具示例
- [../core/permissions.py](../core/permissions.py) - 权限定义（含 API 权限）

---

**最后更新**: 2026-03-22
**适用版本**: OpsClaw v3.0+
