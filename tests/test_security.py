"""测试安全修复 - command_executor_tools 和 main.py"""
import pytest


class TestCommandSecurity:
    """命令执行安全测试"""

    def test_no_password_in_command_line(self):
        """密码不应出现在命令行参数中"""
        import app.tools.command_executor_tools as cet
        import inspect

        src = inspect.getsource(cet)
        assert "-p{" not in src, "密码可能通过命令行参数暴露"

    def test_default_credentials_check_in_startup(self):
        """启动时应检查默认凭据"""
        src = open("app/main.py").read()
        assert "JWT_SECRET_KEY" in src, "启动时未检查 JWT Secret"
        assert "admin123" in src, "启动时未检查默认管理员密码"

    def test_global_exception_handler_exists(self):
        """全局异常处理器存在"""
        src = open("app/main.py").read()
        assert "global_exception_handler" in src
        assert "Internal server error" in src or "内部错误" in src
