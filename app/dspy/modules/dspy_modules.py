"""
真正的 DSPy 模块 - 继承自 dspy.Module

这些模块使用 DSPy 的签名系统，与 DSPy 优化器完全兼容。
"""

import dspy
from typing import Optional


class DataSignature(dspy.Signature):
    """Data Agent 的 DSPy 签名"""
    task_description = dspy.InputField(desc="用户的数据采集任务描述")
    reasoning = dspy.OutputField(desc="Agent 的推理过程和执行计划")


class AnalyzeSignature(dspy.Signature):
    """Analyze Agent 的 DSPy 签名"""
    diagnosis_task = dspy.InputField(desc="诊断任务描述")
    reasoning = dspy.OutputField(desc="分析推理过程和结论")


class ExecuteSignature(dspy.Signature):
    """Execute Agent 的 DSPy 签名"""
    execute_command = dspy.InputField(desc="执行命令描述")
    reasoning = dspy.OutputField(desc="执行推理和结果")


class DataModule(dspy.Module):
    """Data Agent DSPy 模块"""

    def forward(self, task_description: str) -> dspy.Prediction:
        """执行数据采集推理"""
        # 使用 DSPy 的 ChainOfThought
        predict = dspy.ChainOfThought(DataSignature)
        result = predict(task_description=task_description)
        return dspy.Prediction(reasoning=result.reasoning)


class AnalyzeModule(dspy.Module):
    """Analyze Agent DSPy 模块"""

    def forward(self, diagnosis_task: str) -> dspy.Prediction:
        """执行分析诊断推理"""
        predict = dspy.ChainOfThought(AnalyzeSignature)
        result = predict(diagnosis_task=diagnosis_task)
        return dspy.Prediction(reasoning=result.reasoning)


class ExecuteModule(dspy.Module):
    """Execute Agent DSPy 模块"""

    def forward(self, execute_command: str) -> dspy.Prediction:
        """执行操作推理"""
        predict = dspy.ChainOfThought(ExecuteSignature)
        result = predict(execute_command=execute_command)
        return dspy.Prediction(reasoning=result.reasoning)
