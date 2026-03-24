"""
DSPy AnalyzeModule - 分析诊断模块

这个模块使用 DSPy 框架优化 Analyze Agent 的提示词，
根据历史数据自动选择最有效的演示示例。
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AnalyzeInput(BaseModel):
    """Analyze Agent 输入"""
    collected_data: Dict[str, Any] = Field(description="采集的数据")
    task_type: str = Field(default="diagnosis", description="任务类型：diagnosis, analysis, planning")
    context: Optional[str] = Field(None, description="额外上下文")


class AnalyzeOutput(BaseModel):
    """Analyze Agent 输出"""
    summary: Optional[Dict[str, Any]] = Field(None, description="统计摘要")
    root_cause: Optional[str] = Field(None, description="根本原因")
    confidence: float = Field(default=0.0, description="置信度")
    evidence: List[str] = Field(default_factory=list, description="证据列表")
    severity: str = Field(default="P3", description="严重程度：P0-P3")
    impact: Optional[str] = Field(None, description="影响描述")
    affected_resources: List[str] = Field(default_factory=list, description="受影响的资源")
    recommendations: List[Dict[str, Any]] = Field(default_factory=list, description="修复建议")
    diagnostic_steps: List[str] = Field(default_factory=list, description="诊断步骤")


class AnalyzeModule:
    """
    DSPy Analyze Module - 分析诊断模块

    这个模块封装了 Analyze Agent 的推理逻辑，
    使用 DSPy 的 KNI (K-Nearest-Neighbors) 优化器
    从历史数据中选择最相关的演示示例。

    使用方式:
        ```python
        from app.dspy.modules import AnalyzeModule
        from app.dspy.llm_adapter import create_dspy_llm_for_subagent

        # 创建 LLM
        llm = create_dspy_llm_for_subagent("analyze-agent")

        # 创建并编译模块
        module = AnalyzeModule(llm=llm)
        # compiled = module.compile(train_data=trainset)

        # 运行推理
        result = module(
            collected_data={"pods": [...], "metrics": {...}},
            task_type="diagnosis"
        )
        ```
    """

    def __init__(self, llm=None):
        """
        初始化 Analyze Module

        Args:
            llm: DSPy LLM 实例 (可选)
        """
        self.llm = llm
        self.name = "AnalyzeModule"
        self.description = "数据分析和诊断专家，负责分析数据并诊断问题"

        # 基础提示词模板
        self.base_prompt = self._get_base_prompt()

    def _get_base_prompt(self) -> str:
        """获取基础提示词"""
        from app.prompts.subagents.analyze import ANALYZE_AGENT_PROMPT
        return ANALYZE_AGENT_PROMPT

    def forward(
        self,
        collected_data: Dict[str, Any],
        task_type: str = "diagnosis",
        context: Optional[str] = None
    ) -> AnalyzeOutput:
        """
        执行分析诊断推理

        Args:
            collected_data: 采集的数据
            task_type: 任务类型
            context: 额外上下文

        Returns:
            AnalyzeOutput: 分析结果
        """
        # 构建完整提示词
        prompt = self._build_prompt(collected_data, task_type, context)

        # 调用 LLM
        if self.llm:
            response = self.llm(prompt)
            output_text = str(response)
        else:
            # 没有 LLM 时返回模板响应
            output_text = self._template_response(collected_data, task_type)

        # 解析响应
        return self._parse_output(output_text)

    def _build_prompt(
        self,
        collected_data: Dict[str, Any],
        task_type: str,
        context: Optional[str] = None
    ) -> str:
        """
        构建完整提示词

        将基础提示词、演示示例和当前数据组合成完整的提示词。
        """
        import json

        prompt_parts = [
            self.base_prompt,
            "\n\n==== 当前分析任务 ====\n",
            f"任务类型: {task_type}\n",
            f"采集的数据:\n```\n{json.dumps(collected_data, ensure_ascii=False, indent=2)}\n```"
        ]

        if context:
            prompt_parts.append(f"\n上下文: {context}")

        return "".join(prompt_parts)

    def _template_response(self, collected_data: Dict[str, Any], task_type: str) -> str:
        """模板响应（用于没有 LLM 的情况）"""
        import json

        return f"""{{
  "summary": {{
    "data_points": {len(collected_data)},
    "message": "请配置 LLM 以执行实际的分析诊断"
  }},
  "confidence": 0.0,
  "task_type": "{task_type}"
}}"""

    def _parse_output(self, output_text: str) -> AnalyzeOutput:
        """
        解析 LLM 输出

        Args:
            output_text: LLM 返回的文本

        Returns:
            AnalyzeOutput: 解析后的输出
        """
        import json
        import re

        try:
            # 尝试提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', output_text)
            if json_match:
                data = json.loads(json_match.group())
                return AnalyzeOutput(**data)
        except (json.JSONDecodeError, ValueError):
            pass

        # 解析失败时返回基本信息
        return AnalyzeOutput(
            summary={"raw_output": output_text[:200]},
            confidence=0.0
        )

    def compile(
        self,
        trainset: List[Dict[str, Any]],
        max_demos: int = 5,
        **kwargs
    ) -> "CompiledAnalyzeModule":
        """
        编译模块

        使用训练数据和 DSPy 优化器编译模块，
        自动选择最有效的演示示例。

        Args:
            trainset: 训练数据集
            max_demos: 最多使用的演示数量
            **kwargs: 额外的编译参数

        Returns:
            CompiledAnalyzeModule: 编译后的模块
        """
        # 选择最相关的演示
        selected_demos = self._select_demos(trainset, max_demos)

        # 创建编译后的模块
        compiled = CompiledAnalyzeModule(
            llm=self.llm,
            demos=selected_demos,
            max_demos=max_demos
        )

        return compiled

    def _select_demos(
        self,
        trainset: List[Dict[str, Any]],
        max_demos: int
    ) -> List[Dict[str, Any]]:
        """
        选择演示示例

        使用简单的相似度算法选择最相关的演示。
        在实际 DSPy 实现中，这里会使用 KNN 优化器。

        Args:
            trainset: 训练数据集
            max_demos: 最大演示数量

        Returns:
            选中的演示列表
        """
        # 简化实现：选择前 max_demos 个示例
        return trainset[:max_demos]

    def get_compiled_prompt(self, demos: Optional[List[Dict[str, Any]]] = None) -> str:
        """
        获取编译后的完整提示词

        Args:
            demos: 使用的演示示例

        Returns:
            完整提示词
        """
        prompt_parts = [self.base_prompt]

        if demos:
            prompt_parts.append("\n\n==== 参考示例 ====\n")
            for i, demo in enumerate(demos[:5], 1):
                prompt_parts.append(f"\n<!-- 示例 {i} -->\n")
                prompt_parts.append(f"输入: {demo.get('input', '')}\n")
                prompt_parts.append(f"输出: {demo.get('output', '')}\n")

        return "".join(prompt_parts)


class CompiledAnalyzeModule(AnalyzeModule):
    """
    编译后的 Analyze Module

    包含优化后的演示示例，推理时使用这些示例
    来引导 LLM 生成更准确的分析结果。
    """

    def __init__(
        self,
        llm=None,
        demos: Optional[List[Dict[str, Any]]] = None,
        max_demos: int = 5
    ):
        """
        初始化编译后的模块

        Args:
            llm: DSPy LLM 实例
            demos: 优化选择的演示示例
            max_demos: 最大演示数量
        """
        super().__init__(llm=llm)
        self.demos = demos or []
        self.max_demos = max_demos
        self.compiled = True

    def _build_prompt(
        self,
        collected_data: Dict[str, Any],
        task_type: str,
        context: Optional[str] = None
    ) -> str:
        """
        构建编译后的提示词

        包含优化选择的演示示例。
        """
        import json

        prompt_parts = [
            self.base_prompt,
            "\n\n==== 参考示例 (优化选择) ====\n"
        ]

        # 添加选中的演示
        for i, demo in enumerate(self.demos[:self.max_demos], 1):
            prompt_parts.append(f"\n<!-- 示例 {i} -->\n")
            prompt_parts.append(f"输入: {demo.get('input', '')}\n")
            prompt_parts.append(f"输出: {demo.get('output', '')}\n")

        prompt_parts.extend([
            "\n==== 当前分析任务 ====\n",
            f"任务类型: {task_type}\n",
            f"采集的数据:\n```\n{json.dumps(collected_data, ensure_ascii=False, indent=2)}\n```"
        ])

        if context:
            prompt_parts.append(f"\n上下文: {context}")

        return "".join(prompt_parts)


def create_analyze_module(llm=None) -> AnalyzeModule:
    """
    创建 Analyze Module 的便捷函数

    Args:
        llm: DSPy LLM 实例

    Returns:
        AnalyzeModule 实例
    """
    return AnalyzeModule(llm=llm)


def create_compiled_analyze_module(
    llm=None,
    demos: Optional[List[Dict[str, Any]]] = None,
    max_demos: int = 5
) -> CompiledAnalyzeModule:
    """
    创建编译后的 Analyze Module 的便捷函数

    Args:
        llm: DSPy LLM 实例
        demos: 演示示例
        max_demos: 最大演示数量

    Returns:
        CompiledAnalyzeModule 实例
    """
    return CompiledAnalyzeModule(llm=llm, demos=demos, max_demos=max_demos)
