"""
DSPy 模块 - 为 DeepAgents Subagents 提供 DSPy 优化能力

这个模块包含三个核心 DSPy 模块，对应三个主要的 Subagents：
- DataModule: 数据采集模块
- AnalyzeModule: 分析诊断模块
- ExecuteModule: 执行操作模块
"""

# 真正的 DSPy 模块（继承自 dspy.Module，与 DSPy 优化器兼容）
from .dspy_modules import DataModule, AnalyzeModule, ExecuteModule

# 自定义模块（用于非 DSPy 场景）
from .data_module import (
    DataModule as CustomDataModule,
    CompiledDataModule,
    create_data_module as create_custom_data_module,
    create_compiled_data_module,
)
from .analyze_module import (
    AnalyzeModule as CustomAnalyzeModule,
    CompiledAnalyzeModule,
    create_analyze_module as create_custom_analyze_module,
    create_compiled_analyze_module,
)
from .execute_module import (
    ExecuteModule as CustomExecuteModule,
    CompiledExecuteModule,
    create_execute_module as create_custom_execute_module,
    create_compiled_execute_module,
)

# 默认导出真正的 DSPy 模块
__all__ = [
    # DSPy 模块（默认）
    "DataModule",
    "AnalyzeModule",
    "ExecuteModule",
    # 自定义模块（按需使用）
    "CustomDataModule",
    "CustomAnalyzeModule",
    "CustomExecuteModule",
    "CompiledDataModule",
    "CompiledAnalyzeModule",
    "CompiledExecuteModule",
    "create_custom_data_module",
    "create_custom_analyze_module",
    "create_custom_execute_module",
    "create_compiled_data_module",
    "create_compiled_analyze_module",
    "create_compiled_execute_module",
]
