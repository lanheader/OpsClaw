"""测试 DynamicApprovalMiddleware 逻辑"""
import pytest
from unittest.mock import MagicMock, patch


class TestDynamicApprovalMiddleware:
    """动态审批中间件测试"""

    def test_init_without_db(self):
        """不提供 db → 自动创建 session"""
        from app.middleware.dynamic_approval_middleware import DynamicApprovalMiddleware

        with patch("app.middleware.dynamic_approval_middleware.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db
            mock_db.query.return_value.all.return_value = []

            middleware = DynamicApprovalMiddleware(user_id=1)
            assert middleware is not None

    def test_init_no_user_id(self):
        """不提供 user_id → 正常初始化"""
        from app.middleware.dynamic_approval_middleware import DynamicApprovalMiddleware

        middleware = DynamicApprovalMiddleware()
        assert middleware is not None
        assert middleware.user_id is None

    def test_builtin_tools_consistency(self):
        """审批中间件的内置工具列表应与权限中间件一致"""
        from app.middleware.dynamic_approval_middleware import BUILTIN_TOOLS as approval_builtin
        from app.middleware.dynamic_permission_middleware import BUILTIN_TOOLS as perm_builtin

        # 两个中间件的内置工具列表应该包含相同的核心工具
        core_tools = {"write_todos", "task", "read_file", "write_file", "edit_file"}
        for tool in core_tools:
            assert tool in approval_builtin, f"审批中间件缺少内置工具: {tool}"
            assert tool in perm_builtin, f"权限中间件缺少内置工具: {tool}"
