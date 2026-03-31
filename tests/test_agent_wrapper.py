"""测试 DynamicAgentWrapper 和 Agent 创建逻辑"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestDynamicAgentWrapper:
    """DynamicAgentWrapper 测试"""

    def test_wrapper_creation(self):
        """包装器创建"""
        from app.deepagents.main_agent import DynamicAgentWrapper

        mock_agent = MagicMock()
        wrapper = DynamicAgentWrapper(agent=mock_agent, user_permissions={"k8s.read"})
        assert wrapper._agent is mock_agent
        assert "k8s.read" in wrapper._user_permissions

    def test_wrapper_none_permissions(self):
        """无权限 → 正常创建"""
        from app.deepagents.main_agent import DynamicAgentWrapper

        mock_agent = MagicMock()
        wrapper = DynamicAgentWrapper(agent=mock_agent, user_permissions=None)
        assert wrapper._user_permissions is None

    def test_wrapper_getattr_proxy(self):
        """未知属性代理到 base_agent"""
        from app.deepagents.main_agent import DynamicAgentWrapper

        mock_agent = MagicMock()
        mock_agent.some_method = "test_value"
        wrapper = DynamicAgentWrapper(agent=mock_agent)
        assert wrapper.some_method == "test_value"

    @pytest.mark.asyncio
    async def test_wrapper_ainvoke(self):
        """ainvoke 代理调用"""
        from app.deepagents.main_agent import DynamicAgentWrapper

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"messages": []}

        wrapper = DynamicAgentWrapper(agent=mock_agent)
        result = await wrapper.ainvoke({"messages": []}, config={"test": "config"})
        mock_agent.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_wrapper_astream(self):
        """astream 代理调用"""
        from app.deepagents.main_agent import DynamicAgentWrapper

        mock_agent = MagicMock()
        # 模拟 async generator
        async def mock_stream(*args, **kwargs):
            yield {"agent": {"messages": []}}
            yield {"__end__": True}

        mock_agent.astream = mock_stream
        wrapper = DynamicAgentWrapper(agent=mock_agent)

        events = []
        async for event in wrapper.astream({"messages": []}):
            events.append(event)
        assert len(events) == 2


class TestAgentCaching:
    """Agent 缓存测试"""

    def test_invalidate_base_agent(self):
        """缓存清除"""
        from app.deepagents.main_agent import invalidate_base_agent, _base_agent_ready

        invalidate_base_agent()
        assert not _base_agent_ready

    def test_get_thread_config(self):
        """线程配置格式"""
        from app.deepagents.main_agent import get_thread_config

        config = get_thread_config("test-session-123")
        assert config == {"configurable": {"thread_id": "test-session-123"}}
