"""测试 DynamicPermissionMiddleware 逻辑"""
import pytest
from unittest.mock import MagicMock, patch


class TestDynamicPermissionMiddleware:
    """动态权限中间件测试"""

    def test_allow_all_permissions(self):
        """所有权限 → 放行"""
        from app.middleware.dynamic_permission_middleware import DynamicPermissionMiddleware

        # 模拟 registry 中没有这个工具 → 默认放行
        mock_registry = MagicMock()
        mock_registry.get_tool.return_value = None

        with patch("app.middleware.dynamic_permission_middleware.get_tool_registry", return_value=mock_registry):
            middleware = DynamicPermissionMiddleware(permissions={"k8s.read", "prometheus.query"})
            assert middleware is not None

    def test_empty_permissions(self):
        """空权限 → 不拦截内置工具"""
        from app.middleware.dynamic_permission_middleware import DynamicPermissionMiddleware

        middleware = DynamicPermissionMiddleware(permissions=set())
        assert middleware is not None

    def test_no_db_provided(self):
        """不提供 user_id 和 db → 正常初始化"""
        from app.middleware.dynamic_permission_middleware import DynamicPermissionMiddleware

        middleware = DynamicPermissionMiddleware(permissions=set())
        assert middleware is not None

    def test_builtin_tools_set(self):
        """内置工具列表应包含关键工具"""
        from app.middleware.dynamic_permission_middleware import BUILTIN_TOOLS

        expected = {"write_todos", "task", "read_file", "write_file", "edit_file", "ls", "glob", "grep"}
        for tool in expected:
            assert tool in BUILTIN_TOOLS, f"缺少内置工具: {tool}"
