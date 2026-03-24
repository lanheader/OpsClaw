"""Example 数据模型 - 用于 DSPy 训练"""

from enum import Enum
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional


class ExampleType(Enum):
    """示例类型 - 根据任务意图分类"""
    QUERY = "query"       # 查询类：查询集群状态、资源信息
    DIAGNOSE = "diagnose" # 诊断类：问题诊断、根因分析
    EXECUTE = "execute"   # 执行类：执行操作、修复命令


class Example(BaseModel):
    """
    训练示例 - 用于 DSPy 优化

    每个示例包含用户输入（任务描述）和期望的 AI 输出。
    """
    type: ExampleType = Field(description="示例类型")
    input: str = Field(description="用户输入 / 任务描述")
    output: str = Field(description="AI 输出 / 期望结果")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")

    class Config:
        use_enum_values = True


class DataExample(Example):
    """Data Agent 专用示例"""
    tools_used: list[str] = Field(default_factory=list, description="使用的工具列表")
    data_collected: Dict[str, Any] = Field(default_factory=dict, description="采集的数据")


class AnalyzeExample(Example):
    """Analyze Agent 专用示例"""
    root_cause: Optional[str] = Field(None, description="根本原因")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度")
    recommendations: list[str] = Field(default_factory=list, description="修复建议")


class ExecuteExample(Example):
    """Execute Agent 专用示例"""
    operations: list[Dict[str, Any]] = Field(default_factory=list, description="执行的操作")
    verification: Dict[str, Any] = Field(default_factory=dict, description="验证结果")


def create_example(
    example_type: ExampleType,
    input_text: str,
    output_text: str,
    **metadata
) -> Example:
    """
    创建训练示例的便捷函数

    Args:
        example_type: 示例类型
        input_text: 用户输入
        output_text: AI 输出
        **metadata: 额外的元数据

    Returns:
        Example: 训练示例
    """
    # 根据类型选择专门的示例类
    example_classes = {
        ExampleType.QUERY: DataExample,
        ExampleType.DIAGNOSE: AnalyzeExample,
        ExampleType.EXECUTE: ExecuteExample,
    }

    example_class = example_classes.get(example_type, Example)
    return example_class(
        type=example_type,
        input=input_text,
        output=output_text,
        metadata=metadata
    )


def example_to_dspy_format(example: Example):
    """
    将 Example 转换为 DSPy.Example 格式

    Args:
        example: 训练示例

    Returns:
        DSPy Example 对象（模拟）
    """
    # 返回一个简单的字典，DSPy 可以处理
    return {
        "input": example.input,
        "output": example.output,
        "type": example.type.value,
        "metadata": example.metadata
    }
