# app/integrations/feishu/message.py
"""用于构建飞书消息和卡片的工具函数"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from app.utils.logger import get_logger
from app.integrations.feishu.client import get_feishu_client

logger = get_logger(__name__)


async def send_notification(chat_id: str, message: str, level: str = "info") -> bool:
    """
    发送简单文本通知到飞书群聊。

    参数：
        chat_id: 群聊 ID
        message: 通知消息内容
        level: 消息级别（info、success、warning、error）

    返回：
        如果发送成功则返回 True，否则返回 False

    示例：
        success = await send_notification(
            chat_id="oc_xxx",
            message="工作流执行成功",
            level="success"
        )
    """
    try:
        client = get_feishu_client()

        # 添加表情符号和格式化
        emoji_map = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}

        emoji = emoji_map.get(level, "")
        formatted_text = f"{emoji} {message}"

        result = await client.send_text_message(chat_id, formatted_text)

        return result.get("code") == 0

    except Exception as e:
        logger.exception(f"Failed to send notification: {e}")
        return False


async def send_card(chat_id: str, card: Dict[str, Any]) -> Dict[str, Any]:
    """
    发送卡片消息到飞书群聊。

    参数：
        chat_id: 群聊 ID
        card: 卡片内容（JSON 格式）

    返回：
        包含发送结果的字典

    示例：
        card = build_workflow_notification_card(...)
        result = await send_card(chat_id, card)
    """
    try:
        client = get_feishu_client()
        return await client.send_card_message(chat_id, card)

    except Exception as e:
        logger.exception(f"Failed to send card: {e}")
        return {"code": -1, "msg": str(e)}


def build_workflow_notification_card(
    task_id: str,
    task_type: str,
    target_plugin: str,
    status: str,
    success: bool,
    health_status: Optional[str] = None,
    execution_result: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    构建工作流完成通知卡片。

    参数：
        task_id: 任务 ID
        task_type: 任务类型
        target_plugin: 目标插件名称
        status: 工作流状态
        success: 是否成功
        health_status: 健康状态（可选）
        execution_result: 执行结果详情（可选）

    返回：
        飞书卡片 JSON

    示例：
        card = build_workflow_notification_card(
            task_id="task-abc123",
            task_type="scheduled_inspection",
            target_plugin="redis-prod",
            status="completed",
            success=True,
            health_status="healthy"
        )
    """
    # 确定卡片头部颜色和标题
    if success:
        header_color = "green"
        header_emoji = "✅"
        header_text = "工作流完成通知"
    else:
        header_color = "red"
        header_emoji = "❌"
        header_text = "工作流失败通知"

    # 格式化任务类型显示
    task_type_map = {
        "scheduled_inspection": "定期巡检",
        "alert_triggered": "告警触发",
        "manual_command": "手动命令",
        "emergency_response": "紧急响应",
    }
    task_type_display = task_type_map.get(task_type, task_type)

    # 健康状态显示
    health_display = "未知"
    if health_status:
        health_map = {"healthy": "✅ 健康", "degraded": "⚠️ 降级", "unhealthy": "❌ 不健康"}
        health_display = health_map.get(health_status, health_status)

    # 构建卡片
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"{header_emoji} {header_text}"},
            "template": header_color,
        },
        "elements": [
            # 基本信息
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**任务 ID**: `{task_id}`\n"
                        f"**任务类型**: {task_type_display}\n"
                        f"**目标插件**: {target_plugin}\n"
                        f"**状态**: {status}"
                    ),
                },
            },
            {"tag": "hr"},
            # 执行结果
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**健康状态**: {health_display}\n"
                        f"**执行结果**: {'✅ 成功' if success else '❌ 失败'}"
                    ),
                },
            },
        ],
    }

    # 添加执行结果详情（如果有）
    if execution_result:
        details = []

        if "healing_actions_executed" in execution_result:
            actions = execution_result["healing_actions_executed"]
            if actions:
                details.append(f"**执行的修复动作**: {len(actions)} 个")

        if "error" in execution_result:
            details.append(f"**错误信息**: {execution_result['error']}")

        if details:
            card["elements"].append({"tag": "hr"})  # type: ignore[attr-defined]
            card["elements"].append(  # type: ignore[attr-defined]
                {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(details)}}
            )

    return card


def build_approval_card(
    task_id: str,
    target_plugin: str,
    recommended_actions: List[Dict[str, Any]],
    risk_level: int,
    diagnosis: Dict[str, Any],
) -> Dict[str, Any]:
    """
    构建审批请求卡片（带交互按钮）。

    参数：
        task_id: 任务 ID
        target_plugin: 目标插件名称
        recommended_actions: 推荐的修复动作列表
        risk_level: 风险等级（1-10）
        diagnosis: 诊断结果

    返回：
        飞书卡片 JSON（包含交互按钮）

    示例：
        card = build_approval_card(
            task_id="task-abc123",
            target_plugin="redis-prod",
            recommended_actions=[{
                "action_name": "restart_service",
                "expected_impact": "重启 Redis 服务"
            }],
            risk_level=7,
            diagnosis={
                "root_cause": "内存使用过高",
                "issue_severity": "medium"
            }
        )
    """
    # 确定卡片颜色（基于风险等级）
    if risk_level >= 8:
        header_color = "red"
        header_emoji = "🚨"
    elif risk_level >= 5:
        header_color = "orange"
        header_emoji = "⚠️"
    else:
        header_color = "blue"
        header_emoji = "ℹ️"

    # 格式化诊断信息
    root_cause = diagnosis.get("root_cause", "未知")
    issue_severity = diagnosis.get("issue_severity", "未知")

    severity_map = {"low": "🟢 低", "medium": "🟡 中", "high": "🔴 高", "critical": "⛔️ 严重"}
    severity_display = severity_map.get(issue_severity, issue_severity)

    # 格式化推荐动作
    actions_text = ""
    for i, action in enumerate(recommended_actions[:3], 1):  # 最多显示 3 个动作
        action_name = action.get("action_name", "未知动作")
        expected_impact = action.get("expected_impact", "无描述")
        actions_text += f"{i}. **{action_name}**: {expected_impact}\n"

    if not actions_text:
        actions_text = "无推荐动作"

    # 构建卡片
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"{header_emoji} 审批请求 - 风险等级 {risk_level}/10",
            },
            "template": header_color,
        },
        "elements": [
            # 任务信息
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**任务 ID**: `{task_id}`\n"
                        f"**目标插件**: {target_plugin}\n"
                        f"**风险等级**: {risk_level}/10"
                    ),
                },
            },
            {"tag": "hr"},
            # 诊断信息
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (f"**根本原因**: {root_cause}\n" f"**严重性**: {severity_display}"),
                },
            },
            {"tag": "hr"},
            # 推荐动作
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**推荐动作**:\n{actions_text}"}},
            {"tag": "hr"},
            # 交互按钮
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "✅ 批准"},
                        "type": "primary",
                        "value": {"task_id": task_id, "decision": "approved"},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "❌ 拒绝"},
                        "type": "danger",
                        "value": {"task_id": task_id, "decision": "rejected"},
                    },
                ],
            },
        ],
    }

    return card


def build_simple_card(title: str, content: str, color: str = "blue") -> Dict[str, Any]:
    """
    构建简单的通知卡片。

    参数：
        title: 卡片标题
        content: 卡片内容（Markdown 格式）
        color: 卡片颜色（blue、green、red、orange）

    返回：
        飞书卡片 JSON

    示例：
        card = build_simple_card(
            title="系统通知",
            content="**提示**: 数据库备份已完成",
            color="green"
        )
    """
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": title}, "template": color},
        "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": content}}],
    }


def build_table_card(
    title: str,
    headers: List[str],
    rows: List[List[str]],
    summary: Optional[str] = None,
    footer: Optional[str] = None,
    color: str = "blue",
) -> Dict[str, Any]:
    """
    构建带表格的卡片消息

    参数：
        title: 卡片标题
        headers: 表头列表，如 ["NAME", "RESTARTS", "STATUS"]
        rows: 数据行列表，如 [["pod-1", "80", "Running"], ["pod-2", "5", "Running"]]
        summary: 可选的摘要说明（显示在表格上方）
        footer: 可选的底部说明（显示在表格下方）
        color: 卡片颜色

    返回：
        飞书卡片 JSON

    示例：
        card = build_table_card(
            title="Pod 重启统计",
            headers=["NAME", "RESTARTS"],
            rows=[
                ["easy-paas-docker-847c5d49ff-5jl9m", "80"],
                ["tmsbase-xxx", "8"]
            ],
            summary="当前命名空间下共有 **11 个** Pod 存在重启记录",
            footer="⚠️ Pod **easy-paas-docker** 重启次数过高，建议检查"
        )
    """
    elements = []

    # 添加摘要
    if summary:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": summary}})
        elements.append({"tag": "hr"})

    # 添加表头
    header_columns = []
    for header in headers:
        header_columns.append(
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "vertical_align": "top",
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": f"**{header}**"}}
                ],
            }
        )

    elements.append(
        {
            "tag": "column_set",
            "flex_mode": "none",
            "background_style": "grey",
            "columns": header_columns,  # type: ignore[dict-item]
        }
    )

    # 添加数据行
    for row in rows:
        row_columns = []
        for cell in row:
            row_columns.append(
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "vertical_align": "top",
                    "elements": [
                        {"tag": "div", "text": {"tag": "plain_text", "content": str(cell)}}
                    ],
                }
            )

        elements.append({"tag": "column_set", "flex_mode": "none", "columns": row_columns})  # type: ignore[dict-item]

    # 添加底部说明
    if footer:
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": footer}})

    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": title}, "template": color},
        "elements": elements,
    }


def build_formatted_reply_card(
    content: str,
    title: Optional[str] = None,
    color: str = "blue",
    status: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    mention_user_id: Optional[str] = None,  # 新增参数：@用户
) -> Dict[str, Any]:
    """
    构建格式化的回复卡片，支持完整的 Markdown 语法和元数据展示。

    飞书 lark_md 支持的格式：
    - **粗体**
    - *斜体*
    - ~~删除线~~
    - `行内代码`
    - ```代码块```
    - [链接](url)
    - > 引用
    - 有序列表和无序列表

    参数：
        content: 消息内容（支持 Markdown 格式）
        title: 可选的卡片标题（如果不提供则使用默认标题）
        color: 卡片颜色（blue、green、red、orange、grey）
        status: 可选的状态标识（success、warning、error、info、processing）
        metadata: 可选的元数据（如任务ID、耗时等）
        mention_user_id: 可选的用户ID，用于 @用户

    返回：
        飞书卡片 JSON（2.0 格式）

    示例：
        card = build_formatted_reply_card(
            content="**任务 ID**: `task-123`\\n```\\nkubectl get pods\\n```",
            title="任务状态",
            color="blue",
            status="success",
            metadata={"task_id": "task-123", "duration": "2.5s"},
            mention_user_id="ou_xxx"  # @用户
        )
    """
    # 如果需要 @用户，在内容前添加 @
    if mention_user_id:
        content = f"<at user_id=\"{mention_user_id}\"></at> {content}"

    # 如果没有提供标题，使用默认标题
    if not title:
        title = "🤖 OpsClaw"

    # 根据状态添加表情符号
    if status:
        status_emoji_map = {
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
            "info": "ℹ️",
            "processing": "⏳",
        }
        emoji = status_emoji_map.get(status, "")
        if emoji:
            title = f"{emoji} {title}"

    elements = []

    # 添加元数据（如果有）
    if metadata:
        metadata_items = []
        for key, value in metadata.items():
            # 格式化键名（将下划线转为空格，首字母大写）
            formatted_key = key.replace("_", " ").title()
            metadata_items.append(f"**{formatted_key}**: `{value}`")

        if metadata_items:
            elements.append(
                {"tag": "markdown", "content": " | ".join(metadata_items)}
            )
            elements.append({"tag": "hr"})

    # 添加主要内容（使用 markdown 标签，支持表格等更丰富的格式）
    elements.append({"tag": "markdown", "content": content})

    # 添加时间戳
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elements.append({"tag": "hr"})
    elements.append({"tag": "markdown", "content": f"⏰ {timestamp}"})

    # 使用飞书卡片 2.0 格式
    card = {
        "schema": "2.0",  # 关键：指定使用 2.0 版本
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": title}, "template": color},
        "body": {  # 关键：elements 包裹在 body 中
            "elements": elements
        },
    }

    return card


def build_diagnosis_report_card(
    user_input: str,
    collected_data: Dict[str, Any],
    analysis_result: Optional[Dict[str, Any]] = None,
    recommendations: Optional[List[str]] = None,
    task_id: Optional[str] = None,
    duration: Optional[str] = None,
) -> Dict[str, Any]:
    """
    构建诊断报告卡片，展示数据采集和分析结果。

    参数：
        user_input: 用户输入的问题
        collected_data: 采集到的数据
        analysis_result: 分析结果
        recommendations: 建议列表
        task_id: 任务ID
        duration: 执行耗时

    返回：
        飞书卡片 JSON
    """
    elements = []

    # 元数据行
    metadata_items = []
    if task_id:
        metadata_items.append(f"**任务ID**: `{task_id}`")
    if duration:
        metadata_items.append(f"**耗时**: `{duration}`")

    if metadata_items:
        elements.append(
            {"tag": "div", "text": {"tag": "lark_md", "content": " | ".join(metadata_items)}}
        )
        elements.append({"tag": "hr"})

    # 用户问题
    elements.append(
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**📝 用户问题**\n> {user_input}"}}
    )
    elements.append({"tag": "hr"})

    # 数据采集结果
    if collected_data:
        data_summary = []
        for key, value in collected_data.items():
            if isinstance(value, (list, dict)):
                count = len(value)
                data_summary.append(f"- **{key}**: {count} 项")
            else:
                data_summary.append(f"- **{key}**: {value}")

        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**📊 数据采集**\n" + "\n".join(data_summary),
                },
            }
        )
        elements.append({"tag": "hr"})

    # 分析结果
    if analysis_result:
        analysis_content = []
        if "summary" in analysis_result:
            analysis_content.append(f"**摘要**: {analysis_result['summary']}")
        if "root_cause" in analysis_result:
            analysis_content.append(f"**根因**: {analysis_result['root_cause']}")
        if "severity" in analysis_result:
            severity_map = {
                "low": "🟢 低",
                "medium": "🟡 中",
                "high": "🔴 高",
                "critical": "⛔️ 严重",
            }
            severity = severity_map.get(analysis_result["severity"], analysis_result["severity"])
            analysis_content.append(f"**严重性**: {severity}")

        if analysis_content:
            elements.append(
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**🔍 分析结果**\n" + "\n".join(analysis_content),
                    },
                }
            )
            elements.append({"tag": "hr"})

    # 建议
    if recommendations:
        recommendations_text = "\n".join([f"{i+1}. {rec}" for i, rec in enumerate(recommendations)])
        elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**💡 建议**\n{recommendations_text}"},
            }
        )
        elements.append({"tag": "hr"})

    # 时间戳
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elements.append({"tag": "div", "text": {"tag": "plain_text", "content": f"⏰ {timestamp}"}})

    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": "✅ 诊断报告"}, "template": "blue"},
        "elements": elements,
    }
