"""DSPy 数据模块 - 用于训练数据收集和管理"""

from app.dspy.data.examples import (
    Example,
    ExampleType,
    DataExample,
    AnalyzeExample,
    ExecuteExample,
    create_example,
    example_to_dspy_format,
)
from app.dspy.data.collector import (
    TrainingDataCollector,
    collect_training_data,
    collect_training_data_by_date_range,
    get_training_stats,
)

__all__ = [
    "Example",
    "ExampleType",
    "DataExample",
    "AnalyzeExample",
    "ExecuteExample",
    "create_example",
    "example_to_dspy_format",
    "TrainingDataCollector",
    "collect_training_data",
    "collect_training_data_by_date_range",
    "get_training_stats",
]
