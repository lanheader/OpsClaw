"""
DSPy 训练数据收集器

从 chat_sessions 和 chat_messages 表收集对话示例，
用于 DSPy 模块优化。
"""

import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Generator
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from app.models.database import SessionLocal
from app.models.chat_session import ChatSession, SessionState
from app.models.chat_message import ChatMessage, MessageRole
from app.dspy.data.examples import (
    Example,
    ExampleType,
    DataExample,
    AnalyzeExample,
    ExecuteExample,
    create_example,
)


class TrainingDataCollector:
    """
    训练数据收集器

    从数据库中收集高质量的对话示例，用于 DSPy 优化。

    功能：
    - 收集指定时间范围内的对话
    - 自动分类示例类型（query, diagnose, execute）
    - 过滤低质量对话
    - 提取工具调用和结果
    - 生成结构化的训练数据
    """

    # 质量过滤规则
    MIN_USER_MESSAGE_LENGTH = 10  # 最短用户消息长度
    MIN_ASSISTANT_MESSAGE_LENGTH = 20  # 最短助手消息长度
    MAX_EXAMPLES_PER_SESSION = 5  # 每个会话最多提取的示例数

    # 意图关键词（用于自动分类）
    QUERY_KEYWORDS = [
        "查询", "获取", "看看", "显示", "列出", "统计", "多少",
        "状态", "信息", "情况", "怎么样", "有哪些", "详情",
        "get", "show", "list", "check", "status", "info"
    ]

    DIAGNOSE_KEYWORDS = [
        "诊断", "分析", "为什么", "问题", "原因", "错误", "异常",
        "故障", "失败", "排查", "检查", "什么原因", "怎么回事",
        "diagnose", "analyze", "why", "error", "issue", "problem"
    ]

    EXECUTE_KEYWORDS = [
        "重启", "删除", "扩容", "缩容", "更新", "修复", "执行",
        "部署", "回滚", "清理", "创建", "应用", "操作",
        "restart", "delete", "scale", "update", "fix", "deploy"
    ]

    def __init__(self, db: Optional[Session] = None):
        """
        初始化收集器

        Args:
            db: 数据库会话，如果为 None 则创建新的会话
        """
        self.db = db or SessionLocal()
        self._should_close_db = db is None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """关闭数据库连接"""
        if self._should_close_db and self.db:
            self.db.close()

    def collect_by_days(
        self,
        days: int = 7,
        limit: Optional[int] = None
    ) -> List[Example]:
        """
        收集最近 N 天的训练数据

        Args:
            days: 收集最近几天的数据
            limit: 最多收集的示例数量

        Returns:
            训练示例列表
        """
        since = datetime.utcnow() - timedelta(days=days)
        return self.collect_by_date_range(since, datetime.utcnow(), limit)

    def collect_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: Optional[int] = None
    ) -> List[Example]:
        """
        收集指定日期范围的训练数据

        Args:
            start_date: 开始日期
            end_date: 结束日期
            limit: 最多收集的示例数量

        Returns:
            训练示例列表
        """
        # 查询符合条件的会话
        sessions = self._query_sessions(start_date, end_date)

        examples = []
        for session in sessions:
            session_examples = self._extract_examples_from_session(session)
            examples.extend(session_examples)

            if limit and len(examples) >= limit:
                examples = examples[:limit]
                break

        return self._filter_and_rank_examples(examples)

    def _query_sessions(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[ChatSession]:
        """查询指定时间范围的会话"""
        query = (
            self.db.query(ChatSession)
            .filter(
                and_(
                    ChatSession.created_at >= start_date,
                    ChatSession.created_at <= end_date,
                    ChatSession.is_active == True,
                )
            )
            .order_by(desc(ChatSession.created_at))
        )
        return query.all()

    def _extract_examples_from_session(
        self,
        session: ChatSession
    ) -> List[Example]:
        """
        从会话中提取训练示例

        一个会话可能包含多轮对话，每轮对话可以提取一个示例。
        """
        # 查询会话的所有消息
        messages = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.session_id)
            .order_by(ChatMessage.created_at)
            .all()
        )

        examples = []

        # 按用户消息分组，提取用户-助手对话对
        i = 0
        count = 0

        while i < len(messages) and count < self.MAX_EXAMPLES_PER_SESSION:
            user_msg = None
            assistant_msgs = []

            # 查找用户消息
            while i < len(messages) and messages[i].role != MessageRole.USER:
                i += 1

            if i >= len(messages):
                break

            user_msg = messages[i]
            i += 1

            # 收集后续的助手消息
            while i < len(messages) and messages[i].role == MessageRole.ASSISTANT:
                assistant_msgs.append(messages[i])
                i += 1

            # 跳过系统消息
            while i < len(messages) and messages[i].role == MessageRole.SYSTEM:
                i += 1

            # 如果有用户消息和助手消息，提取示例
            if user_msg and assistant_msgs:
                example = self._create_example_from_messages(
                    user_msg,
                    assistant_msgs,
                    session
                )
                if example:
                    examples.append(example)
                    count += 1

        return examples

    def _create_example_from_messages(
        self,
        user_msg: ChatMessage,
        assistant_msgs: List[ChatMessage],
        session: ChatSession
    ) -> Optional[Example]:
        """
        从用户消息和助手消息创建训练示例

        Args:
            user_msg: 用户消息
            assistant_msgs: 助手消息列表
            session: 会话对象

        Returns:
            训练示例或 None
        """
        # 质量检查
        if not self._is_quality_pair(user_msg, assistant_msgs):
            return None

        # 确定示例类型
        example_type = self._classify_example_type(user_msg.content)

        # 组合助手响应
        assistant_content = "\n".join([
            msg.content for msg in assistant_msgs
        ])

        # 提取元数据
        metadata = self._extract_metadata(
            user_msg,
            assistant_msgs,
            session
        )

        # 根据类型创建专门的示例
        if example_type == ExampleType.QUERY:
            return self._create_data_example(
                user_msg.content,
                assistant_content,
                metadata
            )
        elif example_type == ExampleType.DIAGNOSE:
            return self._create_analyze_example(
                user_msg.content,
                assistant_content,
                metadata
            )
        elif example_type == ExampleType.EXECUTE:
            return self._create_execute_example(
                user_msg.content,
                assistant_content,
                metadata
            )
        else:
            return create_example(
                example_type,
                user_msg.content,
                assistant_content,
                **metadata
            )

    def _is_quality_pair(
        self,
        user_msg: ChatMessage,
        assistant_msgs: List[ChatMessage]
    ) -> bool:
        """检查用户-助手消息对是否满足质量要求"""
        # 检查用户消息长度
        if len(user_msg.content) < self.MIN_USER_MESSAGE_LENGTH:
            return False

        # 检查助手消息长度
        total_length = sum(len(msg.content) for msg in assistant_msgs)
        if total_length < self.MIN_ASSISTANT_MESSAGE_LENGTH:
            return False

        # 检查是否有错误
        for msg in assistant_msgs:
            if msg.meta_data:
                try:
                    meta = json.loads(msg.meta_data)
                    if meta.get("error"):
                        return False
                except json.JSONDecodeError:
                    pass

        return True

    def _classify_example_type(self, user_input: str) -> ExampleType:
        """
        根据用户输入分类示例类型

        Args:
            user_input: 用户输入

        Returns:
            示例类型
        """
        user_input_lower = user_input.lower()

        # 计算每种类型的关键词匹配数
        query_score = sum(
            1 for kw in self.QUERY_KEYWORDS
            if kw in user_input_lower
        )
        diagnose_score = sum(
            1 for kw in self.DIAGNOSE_KEYWORDS
            if kw in user_input_lower
        )
        execute_score = sum(
            1 for kw in self.EXECUTE_KEYWORDS
            if kw in user_input_lower
        )

        # 返回得分最高的类型
        scores = {
            ExampleType.QUERY: query_score,
            ExampleType.DIAGNOSE: diagnose_score,
            ExampleType.EXECUTE: execute_score,
        }

        max_score = max(scores.values())
        if max_score == 0:
            return ExampleType.QUERY  # 默认为查询类型

        return max(scores, key=scores.get)

    def _extract_metadata(
        self,
        user_msg: ChatMessage,
        assistant_msgs: List[ChatMessage],
        session: ChatSession
    ) -> Dict[str, Any]:
        """提取元数据"""
        metadata = {
            "session_id": session.session_id,
            "source": session.source,
            "created_at": user_msg.created_at.isoformat(),
        }

        # 提取工具调用信息
        tools_used = set()
        for msg in assistant_msgs:
            if msg.meta_data:
                try:
                    meta = json.loads(msg.meta_data)
                    if "tool_calls" in meta:
                        for call in meta["tool_calls"]:
                            tools_used.add(call.get("tool", "unknown"))
                    if "tools_used" in meta:
                        tools_used.update(meta["tools_used"])
                except json.JSONDecodeError:
                    pass

        if tools_used:
            metadata["tools_used"] = list(tools_used)

        return metadata

    def _create_data_example(
        self,
        input_text: str,
        output_text: str,
        metadata: Dict[str, Any]
    ) -> DataExample:
        """创建 Data Agent 专用示例"""
        return DataExample(
            type=ExampleType.QUERY,
            input=input_text,
            output=output_text,
            tools_used=metadata.get("tools_used", []),
            data_collected={},  # 可以从输出中解析
            metadata=metadata
        )

    def _create_analyze_example(
        self,
        input_text: str,
        output_text: str,
        metadata: Dict[str, Any]
    ) -> AnalyzeExample:
        """创建 Analyze Agent 专用示例"""
        # 尝试从输出中解析分析结果
        root_cause = None
        confidence = 0.0
        recommendations = []

        try:
            # 尝试解析 JSON 输出
            if output_text.strip().startswith("{"):
                result = json.loads(output_text)
                root_cause = result.get("root_cause")
                confidence = result.get("confidence", 0.0)
                recommendations = result.get("recommendations", [])
        except json.JSONDecodeError:
            pass

        return AnalyzeExample(
            type=ExampleType.DIAGNOSE,
            input=input_text,
            output=output_text,
            root_cause=root_cause,
            confidence=confidence,
            recommendations=recommendations,
            metadata=metadata
        )

    def _create_execute_example(
        self,
        input_text: str,
        output_text: str,
        metadata: Dict[str, Any]
    ) -> ExecuteExample:
        """创建 Execute Agent 专用示例"""
        # 尝试从输出中解析执行结果
        operations = []
        verification = {}

        try:
            # 尝试解析 JSON 输出
            if output_text.strip().startswith("{"):
                result = json.loads(output_text)
                operations = result.get("executed_operations", [])
                verification = result.get("verification", {})
        except json.JSONDecodeError:
            pass

        return ExecuteExample(
            type=ExampleType.EXECUTE,
            input=input_text,
            output=output_text,
            operations=operations,
            verification=verification,
            metadata=metadata
        )

    def _filter_and_rank_examples(
        self,
        examples: List[Example]
    ) -> List[Example]:
        """
        过滤和排序示例

        质量评分标准：
        - 输入长度适中（不要太短或太长）
        - 输出结构化（包含 JSON）
        - 包含工具调用
        - 包含具体结果
        """
        scored_examples = []

        for example in examples:
            score = self._calculate_example_score(example)
            if score > 0.3:  # 最低质量阈值
                scored_examples.append((score, example))

        # 按分数排序
        scored_examples.sort(key=lambda x: x[0], reverse=True)

        return [example for _, example in scored_examples]

    def _calculate_example_score(self, example: Example) -> float:
        """
        计算示例质量分数

        Returns:
            0.0 - 1.0 之间的分数
        """
        score = 0.0

        # 输入长度评分（0-0.2）
        input_len = len(example.input)
        if 20 <= input_len <= 200:
            score += 0.2
        elif 10 <= input_len < 20 or 200 < input_len <= 500:
            score += 0.1

        # 输出长度评分（0-0.2）
        output_len = len(example.output)
        if 50 <= output_len <= 2000:
            score += 0.2
        elif 20 <= output_len < 50 or 2000 < output_len <= 5000:
            score += 0.1

        # 结构化输出评分（0-0.3）
        try:
            json.loads(example.output)
            score += 0.3
        except json.JSONDecodeError:
            if "```" in example.output or "json" in example.output.lower():
                score += 0.1

        # 工具调用评分（0-0.3）
        if isinstance(example, DataExample) and example.tools_used:
            score += min(0.3, len(example.tools_used) * 0.1)
        elif "tools_used" in example.metadata:
            tools = example.metadata["tools_used"]
            score += min(0.3, len(tools) * 0.1)

        return score


def collect_training_data(
    days: int = 7,
    limit: Optional[int] = None
) -> List[Example]:
    """
    收集训练数据的便捷函数

    Args:
        days: 收集最近几天的数据
        limit: 最多收集的示例数量

    Returns:
        训练示例列表
    """
    with TrainingDataCollector() as collector:
        return collector.collect_by_days(days, limit)


def collect_training_data_by_date_range(
    start_date: datetime,
    end_date: datetime,
    limit: Optional[int] = None
) -> List[Example]:
    """
    按日期范围收集训练数据的便捷函数

    Args:
        start_date: 开始日期
        end_date: 结束日期
        limit: 最多收集的示例数量

    Returns:
        训练示例列表
    """
    with TrainingDataCollector() as collector:
        return collector.collect_by_date_range(start_date, end_date, limit)


def get_training_stats(days: int = 30) -> Dict[str, Any]:
    """
    获取训练数据统计信息

    Args:
        days: 统计最近几天的数据

    Returns:
        统计信息字典
    """
    with TrainingDataCollector() as collector:
        examples = collector.collect_by_days(days, limit=None)

    # 统计各类型数量
    type_counts = {}
    for example in examples:
        # example.type 可能是 Enum 或字符串（由于 use_enum_values）
        type_name = example.type.value if hasattr(example.type, 'value') else example.type
        type_counts[type_name] = type_counts.get(type_name, 0) + 1

    return {
        "total_examples": len(examples),
        "type_counts": type_counts,
        "days": days,
        "high_quality_examples": len([
            e for e in examples
            if collector._calculate_example_score(e) > 0.7
        ]),
    }
