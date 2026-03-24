"""
工具基类和装饰器

定义统一的工具规范，支持工具自动发现和权限声明。
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, List, Set, Callable
from functools import wraps
import traceback

from app.utils.logger import get_logger, get_request_context

logger = get_logger(__name__)


# ==================== 统一错误处理 ====================

def tool_error_response(
    error: Exception,
    tool_name: str,
    context: Dict[str, Any] = None,
    suggestion: str = None
) -> Dict[str, Any]:
    """
    生成统一的工具错误响应

    Args:
        error: 捕获的异常
        tool_name: 工具名称
        context: 上下文信息（如 namespace, name 等）
        suggestion: 给 Agent 或用户的建议

    Returns:
        标准化的错误响应字典
    """
    error_msg = str(error)
    error_type = type(error).__name__

    # 获取请求上下文
    ctx = get_request_context()
    session_id = ctx.get('session_id', 'no-sess')

    # 根据错误类型生成友好的错误信息
    if "not found" in error_msg.lower() or "404" in error_msg:
        error_type = "NotFound"
        friendly_msg = f"资源不存在: {error_msg}"
        if not suggestion:
            suggestion = "请先使用列表工具（如 get_pods, get_deployments）查看可用资源"

    elif "forbidden" in error_msg.lower() or "403" in error_msg:
        error_type = "PermissionDenied"
        friendly_msg = f"权限不足: {error_msg}"
        if not suggestion:
            suggestion = "请检查当前用户是否有执行此操作的权限"

    elif "unauthorized" in error_msg.lower() or "401" in error_msg:
        error_type = "Unauthorized"
        friendly_msg = f"认证失败: {error_msg}"
        if not suggestion:
            suggestion = "请检查 K8s 集群认证配置"

    elif "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
        error_type = "Timeout"
        friendly_msg = f"操作超时: {error_msg}"
        if not suggestion:
            suggestion = "集群可能负载过高，请稍后重试"

    elif "connection" in error_msg.lower() or "unreachable" in error_msg.lower():
        error_type = "ConnectionError"
        friendly_msg = f"连接失败: {error_msg}"
        if not suggestion:
            suggestion = "请检查网络连接和集群状态"

    elif "invalid" in error_msg.lower() or "validation" in error_msg.lower():
        error_type = "ValidationError"
        friendly_msg = f"参数无效: {error_msg}"
        if not suggestion:
            suggestion = "请检查输入参数是否正确"

    else:
        friendly_msg = f"操作失败: {error_msg}"
        if not suggestion:
            suggestion = "请查看错误详情，或尝试其他操作"

    # 记录错误日志
    logger.error(f"❌ [{session_id}] 工具 {tool_name} 执行失败: {error_type} - {friendly_msg}")

    # 构建响应
    response = {
        "success": False,
        "error": friendly_msg,
        "error_type": error_type,
        "error_detail": error_msg,
        "tool_name": tool_name,
    }

    if context:
        response["context"] = context

    if suggestion:
        response["suggestion"] = suggestion

    return response


def tool_success_response(
    data: Any,
    tool_name: str,
    execution_mode: str = "sdk",
    source: str = None,
    metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    生成统一的工具成功响应

    Args:
        data: 返回的数据
        tool_name: 工具名称
        execution_mode: 执行模式 (sdk/cli)
        source: 数据源标识
        metadata: 额外的元数据

    Returns:
        标准化的成功响应字典
    """
    ctx = get_request_context()
    session_id = ctx.get('session_id', 'no-sess')

    # 记录成功日志
    if isinstance(data, list):
        logger.info(f"✅ [{session_id}] 工具 {tool_name} 执行成功: 返回 {len(data)} 条记录")
    elif isinstance(data, dict):
        logger.info(f"✅ [{session_id}] 工具 {tool_name} 执行成功")
    else:
        logger.info(f"✅ [{session_id}] 工具 {tool_name} 执行成功")

    response = {
        "success": True,
        "data": data,
        "tool_name": tool_name,
        "execution_mode": execution_mode,
    }

    if source:
        response["source"] = source

    if metadata:
        response["metadata"] = metadata

    return response


def with_error_handling(tool_name: str = None):
    """
    工具错误处理装饰器

    用法：
        @with_error_handling("get_pods")
        async def execute(self, namespace: str = "default"):
            # 工具逻辑
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # 获取工具名称
            actual_tool_name = tool_name or self.__class__.__name__
            if actual_tool_name.endswith("Tool"):
                actual_tool_name = actual_tool_name[:-4]

            # 提取上下文信息
            context = {k: v for k, v in kwargs.items() if k in ['namespace', 'name', 'label_selector', 'query']}

            try:
                return await func(self, *args, **kwargs)
            except Exception as e:
                return tool_error_response(
                    error=e,
                    tool_name=actual_tool_name,
                    context=context
                )

        return wrapper
    return decorator


class ToolCategory(str, Enum):
    """工具分类"""
    K8S = "k8s"
    PROMETHEUS = "prometheus"
    LOKI = "loki"
    CHAT = "chat"  # 对话历史工具
    COMMAND = "command"  # 内部降级使用，不暴露给 agent


class OperationType(str, Enum):
    """操作类型"""
    READ = "read"
    WRITE = "write"
    UPDATE = "update"
    DELETE = "delete"


class RiskLevel(str, Enum):
    """风险等级"""
    LOW = "low"        # 只读操作，无风险
    MEDIUM = "medium"  # 可能影响系统性能
    HIGH = "high"      # 可能造成数据丢失或服务中断


class ToolMetadata:
    """工具元数据"""

    def __init__(
        self,
        group: str,                    # 工具分组：k8s.read, k8s.write, prometheus.query
        name: str,                     # 工具名称
        operation_type: OperationType,
        risk_level: RiskLevel,
        permissions: List[str],        # 所需权限列表
        description: str,
        examples: List[str] = None,
        enabled: bool = True,
        expose_to_agent: bool = True,  # 是否暴露给 agent
    ):
        self.group = group
        self.name = name
        self.operation_type = operation_type
        self.risk_level = risk_level
        self.permissions = permissions
        self.description = description
        self.examples = examples or []
        self.enabled = enabled
        self.expose_to_agent = expose_to_agent

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "group": self.group,
            "name": self.name,
            "operation_type": self.operation_type.value,
            "risk_level": self.risk_level.value,
            "permissions": self.permissions,
            "description": self.description,
            "examples": self.examples,
            "enabled": self.enabled,
            "expose_to_agent": self.expose_to_agent,
        }


class BaseOpTool(ABC):
    """
    工具基类

    所有工具类都需要继承此类，并使用 @register_tool 装饰器。
    """

    # 类级别的元数据，由 @register_tool 装饰器设置
    _metadata: Optional[ToolMetadata] = None

    @classmethod
    def get_metadata(cls) -> Optional[ToolMetadata]:
        """获取工具元数据"""
        return cls._metadata

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行工具操作

        Returns:
            {
                "success": bool,
                "data": Any,
                "error": str (可选),
                "execution_mode": "sdk" | "cli",
                "source": str (数据源标识)
            }
        """
        pass

    @classmethod
    def get_langchain_tool(cls):
        """获取 LangChain 工具对象（支持参数签名提取）"""
        if not cls._metadata:
            raise ValueError(f"Tool {cls.__name__} not registered")

        from langchain_core.tools import tool
        from pydantic import BaseModel, Field
        import inspect
        from typing import get_type_hints

        metadata = cls._metadata

        # ========== 提取 execute 方法的签名 ==========
        execute_method = cls.execute
        sig = inspect.signature(execute_method)
        type_hints = get_type_hints(execute_method)

        # 动态构建参数字典
        parameters = {}
        for param_name, param in sig.parameters.items():
            # 跳过 self 和 kwargs 参数
            if param_name in ['self', 'kwargs']:
                continue

            # 获取参数类型
            param_type = type_hints.get(param_name, str)

            # 获取默认值
            if param.default != inspect.Parameter.empty:
                default_value = param.default
                # 为常用参数添加友好的描述
                if param_name == 'namespace':
                    parameters[param_name] = (
                        param_type,
                        Field(
                            default=default_value,
                            description=f"Kubernetes namespace (default: {default_value})"
                        )
                    )
                elif param_name == 'label_selector':
                    parameters[param_name] = (
                        param_type,
                        Field(
                            default=None,
                            description="Label selector to filter resources (e.g., 'app=api')"
                        )
                    )
                else:
                    parameters[param_name] = (
                        param_type,
                        Field(default=default_value, description=f"Parameter: {param_name}")
                    )
            else:
                # 必需参数
                parameters[param_name] = (
                    param_type,
                    Field(description=f"Required parameter: {param_name}")
                )

        # ========== 动态创建 args_schema ==========
        if parameters:
            # 创建动态 Pydantic 模型（Pydantic V2 方式）
            schema_annotations = {}
            schema_fields = {}
            for param_name, (param_type, field) in parameters.items():
                schema_annotations[param_name] = param_type
                schema_fields[param_name] = field

            DynamicArgsSchema = type(
                f"{cls.__name__}Args",
                (BaseModel,),
                {
                    "__annotations__": schema_annotations,
                    **schema_fields  # 直接在类创建时传入字段
                }
            )
        else:
            # 如果没有参数，使用默认的空 schema
            DynamicArgsSchema = None

        # ========== 创建包装函数 ==========
        async def langchain_tool(**kwargs):
            """工具包装函数，支持参数签名提取"""
            instance = cls()
            return await instance.execute(**kwargs)

        # 注意：不要设置 __signature__，让 LangChain 从 args_schema 推断参数
        # 只设置函数名称
        langchain_tool.__name__ = metadata.name
        langchain_tool.__qualname__ = metadata.name

        # 使用 @tool 装饰器，传入 args_schema
        if DynamicArgsSchema:
            tool_obj = tool(
                description=metadata.description,
                args_schema=DynamicArgsSchema
            )(langchain_tool)
        else:
            tool_obj = tool(description=metadata.description)(langchain_tool)

        # 设置 LangChain 工具的元数据
        tool_obj.name = metadata.name
        tool_obj._op_tool_metadata = metadata
        tool_obj._op_tool_class = cls

        return tool_obj


def register_tool(
    group: str,
    operation_type: OperationType,
    risk_level: RiskLevel,
    permissions: List[str],
    description: str,
    examples: List[str] = None,
    enabled: bool = True,
    expose_to_agent: bool = True,
):
    """
    工具注册装饰器

    用法：
        @register_tool(
            group="k8s.read",
            operation_type=OperationType.READ,
            risk_level=RiskLevel.LOW,
            permissions=["k8s.view"],
            description="获取 Kubernetes Pod 列表",
            examples=[
                "get_pods_tool(namespace='default')",
                "get_pods_tool(namespace='production', label_selector='app=api')"
            ]
        )
        class GetPodsTool(BaseOpTool):
            async def execute(self, namespace: str = "default", **kwargs):
                ...
    """
    def decorator(cls):
        # 提取工具名称（去掉 Tool 后缀）
        name = cls.__name__
        if name.endswith("Tool"):
            name = name[:-4]
        # 转换为 snake_case
        import re
        name = re.sub('(?<!^)(?=[A-Z])', '_', name).lower()

        # 创建元数据
        metadata = ToolMetadata(
            group=group,
            name=name,
            operation_type=operation_type,
            risk_level=risk_level,
            permissions=permissions,
            description=description,
            examples=examples,
            enabled=enabled,
            expose_to_agent=expose_to_agent,
        )

        # 设置类级别元数据
        cls._metadata = metadata

        # 自动注册到工具注册表
        from app.tools.registry import ToolRegistry
        ToolRegistry.register_tool_class(cls)

        logger.debug(f"Registered tool: {name} in group {group}")

        return cls

    return decorator


def get_tool_permissions(tool) -> List[str]:
    """
    从工具对象提取权限要求

    Args:
        tool: LangChain 工具对象或 BaseOpTool 实例

    Returns:
        权限代码列表
    """
    # 如果是 LangChain 工具对象
    if hasattr(tool, '_op_tool_metadata'):
        return tool._op_tool_metadata.permissions

    # 如果是 BaseOpTool 类
    if isinstance(tool, type) and issubclass(tool, BaseOpTool):
        metadata = tool.get_metadata()
        if metadata:
            return metadata.permissions

    return []


__all__ = [
    "ToolCategory",
    "OperationType",
    "RiskLevel",
    "ToolMetadata",
    "BaseOpTool",
    "register_tool",
    "get_tool_permissions",
    "tool_error_response",
    "tool_success_response",
    "with_error_handling",
]
