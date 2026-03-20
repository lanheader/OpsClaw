# app/models/tool_metadata.py
"""工具元数据模型"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class ToolCategory(str, Enum):
    """工具分类"""

    K8S = "k8s"
    PROMETHEUS = "prometheus"
    LOGS = "logs"
    ALERT = "alert"
    SYSTEM = "system"
    DATABASE = "database"
    NETWORK = "network"


class RiskLevel(int, Enum):
    """风险等级"""

    SAFE = 0  # 完全安全（只读操作）
    LOW = 3  # 低风险（轻微修改）
    MEDIUM = 6  # 中等风险（重要修改）
    HIGH = 9  # 高风险（危险操作）
    CRITICAL = 10  # 极高风险（不可逆操作）


@dataclass
class ToolParameter:
    """工具参数"""

    name: str
    type: str
    required: bool
    description: str
    default: Optional[Any] = None
    examples: List[str] = field(default_factory=list)


@dataclass
class ToolMetadata:
    """工具元数据"""

    tool_id: str  # 工具唯一标识（函数名）
    name: str  # 工具显示名称
    description: str  # 工具用途描述
    category: ToolCategory  # 工具分类
    risk_level: RiskLevel  # 风险等级
    parameters: List[ToolParameter]  # 参数列表
    examples: List[str] = field(default_factory=list)  # 使用示例
    requires_approval: bool = False  # 是否需要审批
    command_template: Optional[str] = None  # 命令模板（用于显示）

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "risk_level": self.risk_level.value,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "required": p.required,
                    "description": p.description,
                    "default": p.default,
                    "examples": p.examples,
                }
                for p in self.parameters
            ],
            "examples": self.examples,
            "requires_approval": self.requires_approval,
            "command_template": self.command_template,
        }

    def format_for_user(self, params: Dict[str, Any]) -> str:
        """
        格式化为用户友好的描述

        Args:
            params: 实际参数值

        Returns:
            格式化后的描述字符串
        """
        # 风险等级图标
        risk_icons = {
            RiskLevel.SAFE: "🟢",
            RiskLevel.LOW: "🟡",
            RiskLevel.MEDIUM: "🟠",
            RiskLevel.HIGH: "🔴",
            RiskLevel.CRITICAL: "⛔",
        }

        # 风险等级文本
        risk_texts = {
            RiskLevel.SAFE: "安全（只读操作）",
            RiskLevel.LOW: "低风险",
            RiskLevel.MEDIUM: "中等风险",
            RiskLevel.HIGH: "高风险",
            RiskLevel.CRITICAL: "极高风险",
        }

        risk_icon = risk_icons.get(self.risk_level, "❓")
        risk_text = risk_texts.get(self.risk_level, "未知")

        # 构建命令字符串
        if self.command_template:
            # 替换模板中的参数
            command = self.command_template
            for key, value in params.items():
                command = command.replace(f"{{{key}}}", str(value))
        else:
            # 默认格式
            param_str = " ".join([f"{k}={v}" for k, v in params.items()])
            command = f"{self.tool_id} {param_str}"

        return f"""【{self.name}】
   工具: {self.tool_id}
   用途: {self.description}
   风险: {risk_icon} {risk_text}
   命令: `{command}`"""
