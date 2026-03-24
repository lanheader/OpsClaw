"""
DSPy ExecuteModule - 执行操作模块

这个模块使用 DSPy 框架优化 Execute Agent 的提示词，
根据历史数据自动选择最有效的演示示例。
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ExecuteInput(BaseModel):
    """Execute Agent 输入"""
    commands: List[Dict[str, Any]] = Field(description="要执行的命令列表")
    approval_status: str = Field(default="approved", description="批准状态")
    context: Optional[str] = Field(None, description="额外上下文")


class ExecuteOperation(BaseModel):
    """执行的操作"""
    action: str = Field(description="操作类型")
    resource: str = Field(description="目标资源")
    namespace: Optional[str] = Field(None, description="命名空间")
    status: str = Field(description="操作状态")
    details: str = Field(default="", description="执行详情")
    execution_time: float = Field(default=0.0, description="耗时（秒）")


class ExecuteOutput(BaseModel):
    """Execute Agent 输出"""
    success: bool = Field(description="整体是否成功")
    executed_operations: List[ExecuteOperation] = Field(
        default_factory=list,
        description="执行的操作列表"
    )
    verification: Dict[str, Any] = Field(
        default_factory=dict,
        description="验证结果"
    )
    errors: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="错误列表"
    )
    rollback_info: Dict[str, Any] = Field(
        default_factory=dict,
        description="回滚信息"
    )


class ExecuteModule:
    """
    DSPy Execute Module - 执行操作模块

    这个模块封装了 Execute Agent 的推理逻辑，
    使用 DSPy 的 KNI (K-Nearest-Neighbors) 优化器
    从历史数据中选择最相关的演示示例。

    使用方式:
        ```python
        from app.dspy.modules import ExecuteModule
        from app.dspy.llm_adapter import create_dspy_llm_for_subagent

        # 创建 LLM
        llm = create_dspy_llm_for_subagent("execute-agent")

        # 创建并编译模块
        module = ExecuteModule(llm=llm)
        # compiled = module.compile(train_data=trainset)

        # 运行推理
        result = module(
            commands=[{"action": "restart_deployment", "resource": "nginx"}],
            approval_status="approved"
        )
        ```
    """

    def __init__(self, llm=None):
        """
        初始化 Execute Module

        Args:
            llm: DSPy LLM 实例 (可选)
        """
        self.llm = llm
        self.name = "ExecuteModule"
        self.description = "操作执行专家，负责执行经过审核的修复命令"

        # 基础提示词模板
        self.base_prompt = self._get_base_prompt()

    def _get_base_prompt(self) -> str:
        """获取基础提示词"""
        from app.prompts.subagents.execute import EXECUTE_AGENT_PROMPT
        return EXECUTE_AGENT_PROMPT

    def forward(
        self,
        commands: List[Dict[str, Any]],
        approval_status: str = "approved",
        context: Optional[str] = None
    ) -> ExecuteOutput:
        """
        执行操作推理

        Args:
            commands: 要执行的命令列表
            approval_status: 批准状态
            context: 额外上下文

        Returns:
            ExecuteOutput: 执行结果
        """
        # 检查批准状态
        if approval_status != "approved":
            return ExecuteOutput(
                success=False,
                errors=[{
                    "operation": "执行",
                    "error": f"命令未获得批准，当前状态: {approval_status}",
                    "suggestion": "请等待用户批准后再执行"
                }]
            )

        # 构建完整提示词
        prompt = self._build_prompt(commands, context)

        # 调用 LLM
        if self.llm:
            response = self.llm(prompt)
            output_text = str(response)
        else:
            # 没有 LLM 时返回模板响应
            output_text = self._template_response(commands)

        # 解析响应
        return self._parse_output(output_text)

    def _build_prompt(
        self,
        commands: List[Dict[str, Any]],
        context: Optional[str] = None
    ) -> str:
        """
        构建完整提示词

        将基础提示词、演示示例和当前命令组合成完整的提示词。
        """
        import json

        prompt_parts = [
            self.base_prompt,
            "\n\n==== 当前执行任务 ====\n",
            "批准状态: 已批准\n",
            f"执行命令:\n```\n{json.dumps(commands, ensure_ascii=False, indent=2)}\n```"
        ]

        if context:
            prompt_parts.append(f"\n上下文: {context}")

        return "".join(prompt_parts)

    def _template_response(self, commands: List[Dict[str, Any]]) -> str:
        """模板响应（用于没有 LLM 的情况）"""
        import json

        operations = []
        for cmd in commands:
            operations.append({
                "action": cmd.get("action", "unknown"),
                "resource": cmd.get("resource", ""),
                "namespace": cmd.get("namespace", ""),
                "status": "pending",
                "details": "请配置 LLM 以执行实际的操作",
                "execution_time": 0.0
            })

        return json.dumps({
            "success": False,
            "executed_operations": operations,
            "verification": {"verified": False, "message": "需要配置 LLM"},
            "errors": [],
            "rollback_info": {"can_rollback": False}
        }, ensure_ascii=False)

    def _parse_output(self, output_text: str) -> ExecuteOutput:
        """
        解析 LLM 输出

        Args:
            output_text: LLM 返回的文本

        Returns:
            ExecuteOutput: 解析后的输出
        """
        import json
        import re

        try:
            # 尝试提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', output_text)
            if json_match:
                data = json.loads(json_match.group())

                # 转换 executed_operations
                if "executed_operations" in data:
                    ops = []
                    for op in data["executed_operations"]:
                        if isinstance(op, dict):
                            ops.append(ExecuteOperation(**op))
                        else:
                            ops.append(op)
                    data["executed_operations"] = ops

                return ExecuteOutput(**data)
        except (json.JSONDecodeError, ValueError):
            pass

        # 解析失败时返回基本信息
        return ExecuteOutput(
            success=False,
            verification={"verified": False, "raw_output": output_text[:200]}
        )

    def compile(
        self,
        trainset: List[Dict[str, Any]],
        max_demos: int = 5,
        **kwargs
    ) -> "CompiledExecuteModule":
        """
        编译模块

        使用训练数据和 DSPy 优化器编译模块，
        自动选择最有效的演示示例。

        Args:
            trainset: 训练数据集
            max_demos: 最多使用的演示数量
            **kwargs: 额外的编译参数

        Returns:
            CompiledExecuteModule: 编译后的模块
        """
        # 选择最相关的演示
        selected_demos = self._select_demos(trainset, max_demos)

        # 创建编译后的模块
        compiled = CompiledExecuteModule(
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


class CompiledExecuteModule(ExecuteModule):
    """
    编译后的 Execute Module

    包含优化后的演示示例，推理时使用这些示例
    来引导 LLM 生成更准确的执行计划。
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
        commands: List[Dict[str, Any]],
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
            "\n==== 当前执行任务 ====\n",
            "批准状态: 已批准\n",
            f"执行命令:\n```\n{json.dumps(commands, ensure_ascii=False, indent=2)}\n```"
        ])

        if context:
            prompt_parts.append(f"\n上下文: {context}")

        return "".join(prompt_parts)


def create_execute_module(llm=None) -> ExecuteModule:
    """
    创建 Execute Module 的便捷函数

    Args:
        llm: DSPy LLM 实例

    Returns:
        ExecuteModule 实例
    """
    return ExecuteModule(llm=llm)


def create_compiled_execute_module(
    llm=None,
    demos: Optional[List[Dict[str, Any]]] = None,
    max_demos: int = 5
) -> CompiledExecuteModule:
    """
    创建编译后的 Execute Module 的便捷函数

    Args:
        llm: DSPy LLM 实例
        demos: 演示示例
        max_demos: 最大演示数量

    Returns:
        CompiledExecuteModule 实例
    """
    return CompiledExecuteModule(llm=llm, demos=demos, max_demos=max_demos)
