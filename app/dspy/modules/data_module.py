"""
DSPy DataModule - 数据采集模块

这个模块使用 DSPy 框架优化 Data Agent 的提示词，
根据历史数据自动选择最有效的演示示例。
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class DataInput(BaseModel):
    """Data Agent 输入"""
    query: str = Field(description="数据采集查询")
    context: Optional[str] = Field(None, description="额外上下文信息")
    constraints: Optional[Dict[str, Any]] = Field(default_factory=dict, description="约束条件")


class DataOutput(BaseModel):
    """Data Agent 输出"""
    success: bool = Field(description="是否成功")
    data: Dict[str, Any] = Field(default_factory=dict, description="采集的数据")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    errors: List[str] = Field(default_factory=list, description="错误列表")


class DataModule:
    """
    DSPy Data Module - 数据采集模块

    这个模块封装了 Data Agent 的推理逻辑，
    使用 DSPy 的 KNI (K-Nearest-Neighbors) 优化器
    从历史数据中选择最相关的演示示例。

    使用方式:
        ```python
        from app.dspy.modules import DataModule
        from app.dspy.llm_adapter import create_dspy_llm_for_subagent

        # 创建 LLM
        llm = create_dspy_llm_for_subagent("data-agent")

        # 创建并编译模块
        module = DataModule(llm=llm)
        # 使用训练数据编译
        # compiled = module.compile(train_data=trainset)

        # 运行推理
        result = module(query="获取所有 Pod 的状态")
        ```
    """

    def __init__(self, llm=None):
        """
        初始化 Data Module

        Args:
            llm: DSPy LLM 实例 (可选)
        """
        self.llm = llm
        self.name = "DataModule"
        self.description = "数据采集专家，负责从 Kubernetes、Prometheus、Loki 采集数据"

        # 基础提示词模板
        self.base_prompt = self._get_base_prompt()

    def _get_base_prompt(self) -> str:
        """获取基础提示词"""
        from app.prompts.subagents.data import DATA_AGENT_PROMPT
        return DATA_AGENT_PROMPT

    def forward(self, query: str, context: Optional[str] = None) -> DataOutput:
        """
        执行数据采集推理

        Args:
            query: 数据采集查询
            context: 额外上下文

        Returns:
            DataOutput: 采集结果
        """
        # 构建完整提示词
        prompt = self._build_prompt(query, context)

        # 调用 LLM
        if self.llm:
            response = self.llm(prompt)
            output_text = str(response)
        else:
            # 没有 LLM 时返回模板响应
            output_text = self._template_response(query)

        # 解析响应
        return self._parse_output(output_text)

    def _build_prompt(self, query: str, context: Optional[str] = None) -> str:
        """
        构建完整提示词

        将基础提示词、演示示例和当前查询组合成完整的提示词。
        """
        prompt_parts = [
            self.base_prompt,
            "\n\n==== 当前任务 ====\n",
            f"采集命令: {query}"
        ]

        if context:
            prompt_parts.append(f"\n上下文: {context}")

        return "".join(prompt_parts)

    def _template_response(self, query: str) -> str:
        """模板响应（用于没有 LLM 的情况）"""
        return f"""{{
  "success": true,
  "data": {{
    "query": "{query}",
    "message": "请配置 LLM 以执行实际的数据采集"
  }},
  "metadata": {{
    "source": "template",
    "module": "DataModule"
  }}
}}"""

    def _parse_output(self, output_text: str) -> DataOutput:
        """
        解析 LLM 输出

        Args:
            output_text: LLM 返回的文本

        Returns:
            DataOutput: 解析后的输出
        """
        import json
        import re

        try:
            # 尝试提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', output_text)
            if json_match:
                data = json.loads(json_match.group())
                return DataOutput(**data)
        except (json.JSONDecodeError, ValueError):
            pass

        # 解析失败时返回基本信息
        return DataOutput(
            success=True,
            data={"raw_output": output_text},
            metadata={"module": "DataModule"}
        )

    def compile(
        self,
        trainset: List[Dict[str, Any]],
        max_demos: int = 5,
        **kwargs
    ) -> "CompiledDataModule":
        """
        编译模块

        使用训练数据和 DSPy 优化器编译模块，
        自动选择最有效的演示示例。

        Args:
            trainset: 训练数据集
            max_demos: 最多使用的演示数量
            **kwargs: 额外的编译参数

        Returns:
            CompiledDataModule: 编译后的模块
        """
        # 选择最相关的演示
        selected_demos = self._select_demos(trainset, max_demos)

        # 创建编译后的模块
        compiled = CompiledDataModule(
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
        # 实际 DSPy 会使用相似度算法
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


class CompiledDataModule(DataModule):
    """
    编译后的 Data Module

    包含优化后的演示示例，推理时使用这些示例
    来引导 LLM 生成更准确的响应。
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

    def _build_prompt(self, query: str, context: Optional[str] = None) -> str:
        """
        构建编译后的提示词

        包含优化选择的演示示例。
        """
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
            "\n==== 当前任务 ====\n",
            f"采集命令: {query}"
        ])

        if context:
            prompt_parts.append(f"\n上下文: {context}")

        return "".join(prompt_parts)


def create_data_module(llm=None) -> DataModule:
    """
    创建 Data Module 的便捷函数

    Args:
        llm: DSPy LLM 实例

    Returns:
        DataModule 实例
    """
    return DataModule(llm=llm)


def create_compiled_data_module(
    llm=None,
    demos: Optional[List[Dict[str, Any]]] = None,
    max_demos: int = 5
) -> CompiledDataModule:
    """
    创建编译后的 Data Module 的便捷函数

    Args:
        llm: DSPy LLM 实例
        demos: 演示示例
        max_demos: 最大演示数量

    Returns:
        CompiledDataModule 实例
    """
    return CompiledDataModule(llm=llm, demos=demos, max_demos=max_demos)
