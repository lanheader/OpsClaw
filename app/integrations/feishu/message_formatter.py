"""飞书消息格式化工具 - 让消息像人类交流一样自然"""

from typing import Dict, List, Any, Optional


def format_approval_request(
    commands: List[Dict[str, Any]], risk_level: str = "未知", user_input: str = ""
) -> str:
    """
    格式化批准请求消息 - 自然、清晰、友好

    Args:
        commands: 计划执行的命令列表
        risk_level: 风险等级
        user_input: 用户的原始输入

    Returns:
        格式化后的消息文本
    """
    # 处理 None 值
    if commands is None:
        commands = []
    if risk_level is None:
        risk_level = "未知"

    # 格式化命令列表
    commands_text = ""
    for i, cmd in enumerate(commands, 1):
        action_desc = _format_command_friendly(cmd)
        reason = cmd.get("reason", "")

        commands_text += f"{i}. {action_desc}\n"
        if reason:
            commands_text += f"   💡 {reason}\n"

    # 根据风险等级调整语气
    risk_emoji = "⚠️"
    risk_desc = "中等风险"

    if "高" in risk_level or "严重" in risk_level:
        risk_emoji = "🚨"
        risk_desc = "高风险操作"
    elif "低" in risk_level or "安全" in risk_level:
        risk_emoji = "✅"
        risk_desc = "低风险操作"

    # 构建自然的消息
    message = f"""好的，我明白你的需求了。

为了帮你解决问题，我需要执行以下操作：

{commands_text}
{risk_emoji} 风险评估：{risk_desc}

你同意我执行这些操作吗？
• 回复"同意"或"可以" - 我会立即开始
• 回复"不要"或"取消" - 我会停止
• 有疑问？直接问我就好"""

    return message


def format_execution_progress(step: str, total: int, current: int) -> str:
    """
    格式化执行进度消息

    Args:
        step: 当前步骤描述
        total: 总步骤数
        current: 当前步骤编号

    Returns:
        格式化后的进度消息
    """
    progress_bar = "▓" * current + "░" * (total - current)

    return f"""⏳ 正在执行 ({current}/{total})

{progress_bar}

当前步骤：{step}"""


def format_completion_report(
    user_input: str,
    collected_data: Dict[str, Any],
    analysis_result: Optional[Dict[str, Any]] = None,
    execution_result: Optional[Dict[str, Any]] = None,
    duration: Optional[float] = None,
) -> str:
    """
    格式化完成报告 - 简洁、有用、易读

    Args:
        user_input: 用户的原始问题
        collected_data: 采集到的数据
        analysis_result: 分析结果
        execution_result: 执行结果
        duration: 执行耗时（秒）

    Returns:
        格式化后的报告
    """
    # 开头
    report = "✅ 搞定了！\n\n"

    # 问题回顾
    report += f"你问的是：{user_input}\n\n"

    # 发现的情况
    if analysis_result:
        has_issue = analysis_result.get("has_issue", False)

        if has_issue:
            issue_summary = analysis_result.get("issue_summary", "发现了一些问题")
            severity = analysis_result.get("severity", "medium")

            severity_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴", "critical": "⛔"}.get(
                severity, "🟡"
            )

            report += f"{severity_emoji} 发现的问题：\n{issue_summary}\n\n"

            # 根因（如果有）
            root_cause = analysis_result.get("root_cause")
            if root_cause:
                report += f"🔍 根本原因：\n{root_cause}\n\n"
        else:
            report += "✅ 一切正常，没有发现问题\n\n"

    # 执行的操作（如果有）
    if execution_result and execution_result.get("success"):
        actions = execution_result.get("actions_taken", [])
        if actions:
            report += "🔧 我做了这些：\n"
            for action in actions:
                report += f"• {action}\n"
            report += "\n"

    # 数据摘要（简化版）
    if collected_data:
        data_count = len(collected_data)
        report += f"📊 采集了 {data_count} 类数据\n\n"

    # 建议（如果有）
    if analysis_result:
        recommendations = analysis_result.get("recommendations", [])
        if recommendations:
            report += "💡 建议：\n"
            for rec in recommendations[:3]:  # 最多显示3条
                report += f"• {rec}\n"
            report += "\n"

    # 耗时
    if duration:
        report += f"⏱️ 用时 {duration:.1f} 秒\n"

    return report


def format_error_message(error: Exception, user_friendly: bool = True) -> str:
    """
    格式化错误消息 - 友好、有帮助

    Args:
        error: 异常对象
        user_friendly: 是否使用用户友好的语言

    Returns:
        格式化后的错误消息
    """
    if user_friendly:
        # 根据错误类型提供友好的解释
        error_str = str(error).lower()

        if "timeout" in error_str or "超时" in error_str:
            return """⏰ 抱歉，操作超时了

可能是因为：
• 系统响应比较慢
• 网络连接不稳定

你可以：
• 稍等一会儿再试
• 简化一下你的请求"""

        elif "permission" in error_str or "权限" in error_str:
            return """🔒 权限不足

看起来我没有权限执行这个操作。

请联系管理员检查权限配置。"""

        elif "not found" in error_str or "未找到" in error_str:
            return """🔍 找不到资源

我没有找到你要查询的资源。

请检查：
• 名称是否正确
• 资源是否存在"""

        else:
            return f"""❌ 出了点问题

{str(error)}

如果问题持续，请联系技术支持。"""
    else:
        # 技术详细错误（用于调试）
        return f"❌ 错误：{str(error)}"


def format_help_message() -> str:
    """
    格式化帮助消息 - 简洁、友好

    Returns:
        格式化后的帮助消息
    """
    return """👋 你好！我是运维助手

我能帮你：
• 查看集群和服务状态
• 诊断系统问题
• 执行运维操作
• 生成巡检报告

直接告诉我你想做什么就行，比如：
"查一下 user-service 的状态"
"应用响应很慢，帮我看看"
"检查一下 Redis 的内存"

📋 可用命令：
• /help - 显示此帮助信息
• /new - 创建新会话（开始新对话）
• /end - 结束当前会话（保存历史）

有问题随时问我 😊"""


def format_clarification_request(commands_summary: str, risk_level: str) -> str:
    """
    格式化澄清请求消息

    Args:
        commands_summary: 命令摘要
        risk_level: 风险等级

    Returns:
        格式化后的澄清消息
    """
    return f"""让我再确认一下：

我准备执行：
{commands_summary}

风险等级：{risk_level}

你是同意还是拒绝？
• 同意 → 回复"同意"、"可以"、"执行"
• 拒绝 → 回复"不要"、"取消"、"拒绝"

有疑问也可以直接问我。"""


def format_approval_confirmed(decision: str) -> str:
    """
    格式化批准确认消息

    Args:
        decision: 批准决定（approved/rejected）

    Returns:
        格式化后的确认消息
    """
    if decision == "approved":
        return "✅ 收到，马上开始执行..."
    else:
        return "❌ 好的，已取消操作"


def format_insufficient_confidence(confidence: float, approval_data: Dict[str, Any]) -> str:
    """
    格式化置信度不足消息

    Args:
        confidence: 置信度
        approval_data: 批准数据

    Returns:
        格式化后的消息
    """
    commands_summary = approval_data.get("commands_summary", "未知操作")

    return f"""🤔 我不太确定你的意思（置信度：{confidence:.0%}）

你还有一个待批准的操作：
{commands_summary}

请明确告诉我：
• 同意 → 我会执行
• 拒绝 → 我会取消

这样我就能理解了 😊"""


def format_pending_approval_warning(approval_data: Dict[str, Any]) -> str:
    """
    格式化待批准警告消息

    Args:
        approval_data: 批准数据

    Returns:
        格式化后的警告消息
    """
    commands_summary = approval_data.get("commands_summary", "未知操作")

    return f"""⚠️ 等一下

你还有一个操作没处理：
{commands_summary}

请先告诉我是同意还是拒绝，然后我再处理你的新请求。"""


import re


def clean_xml_tags(content: str) -> str:
    """
    清理消息中的 XML 标签，保留内容

    清理的标签包括：
    - <result>...</result>
    - <summary>...</summary>
    - <details>...</details>
    - <next_steps>...</next_steps>
    - 以及其他类似的 XML 标签

    Args:
        content: 原始内容

    Returns:
        清理后的内容
    """
    if not content:
        return content

    # 定义需要清理的 XML 标签模式
    # 这些标签通常用于结构化输出，但在飞书中显示时需要移除
    xml_patterns = [
        # 常见的结构化标签
        (r'<result>(.*?)</result>', r'\1'),
        (r'<summary>(.*?)</summary>', r'\1'),
        (r'<details>(.*?)</details>', r'\1'),
        (r'<next_steps>(.*?)</next_steps>', r'\1'),
        (r'<root_cause>(.*?)</root_cause>', r'\1'),
        (r'<recommendations>(.*?)</recommendations>', r'\1'),
        (r'<execution_details>(.*?)</execution_details>', r'\1'),
        (r'<error>(.*?)</error>', r'\1'),
        # 自闭合标签
        (r'<result\s*/>', ''),
        (r'<summary\s*/>', ''),
        (r'<details\s*/>', ''),
        (r'<next_steps\s*/>', ''),
        # 任何其他 XML 标签（保留内容）
        (r'<(\w+)>([^<]+)</\1>', r'\2'),
        (r'<(\w+)\s*/>', ''),
    ]

    cleaned_content = content
    for pattern, replacement in xml_patterns:
        cleaned_content = re.sub(pattern, replacement, cleaned_content, flags=re.DOTALL)

    # 清理多余的空行（超过2个连续换行的情况）
    cleaned_content = re.sub(r'\n{3,}', '\n\n', cleaned_content)

    return cleaned_content.strip()


def _format_command_friendly(cmd: Dict[str, Any]) -> str:
    """
    将命令格式化为用户友好的描述

    Args:
        cmd: 命令字典

    Returns:
        友好的命令描述
    """
    cmd_type = cmd.get("type", "")
    action = cmd.get("action", "")
    params = cmd.get("params", {})

    # K8s 操作
    if cmd_type == "k8s":
        if action in {"get_pod_status", "list_pods", "get_pods"}:
            pod_name = params.get("pod_name", "")
            namespace = params.get("namespace", "default")
            if pod_name:
                return f"查看 Pod {pod_name} 的状态"
            return f"列出命名空间 {namespace} 下的 Pod 列表"
        elif action == "get_pod_logs":
            pod_name = params.get("pod_name", "")
            return f"获取 Pod {pod_name} 的日志"
        elif action == "get_deployment_status":
            deployment = params.get("deployment", "")
            return f"查看 Deployment {deployment} 的状态"
        elif action == "get_service_status":
            service = params.get("service", "")
            return f"查看 Service {service} 的状态"
        elif action == "get_node_status":
            return "查看集群节点状态"
        else:
            return f"执行 Kubernetes 操作：{action}"

    # Prometheus 操作
    elif cmd_type == "prometheus":
        if action == "query_metrics":
            query = params.get("query", "")
            return f"查询监控指标：{query}"
        elif action == "query_range":
            query = params.get("query", "")
            duration = params.get("duration", "5m")
            return f"查询最近 {duration} 的指标：{query}"
        else:
            return f"查询 Prometheus 指标"

    # 日志操作
    elif cmd_type == "logs":
        if action == "get_pod_logs":
            pod_name = params.get("pod_name", "")
            return f"获取 Pod {pod_name} 的日志"
        elif action == "query_loki":
            return "查询日志系统"
        else:
            return "查询日志"

    # 告警操作
    elif cmd_type == "alert":
        if action == "get_active_alerts":
            return "查询当前活跃告警"
        elif action == "get_alert_history":
            duration = params.get("duration", "1h")
            return f"查询最近 {duration} 的告警历史"
        else:
            return "查询告警信息"

    # 默认
    else:
        return f"执行 {cmd_type} 操作：{action}"
