"""测试模块导入 - 确保所有改动后的模块都能正常导入"""
import pytest


class TestImports:
    """模块导入测试"""

    def test_main_agent_imports(self):
        from app.deepagents.main_agent import (
            get_ops_agent,
            create_base_agent,
            get_cached_base_agent,
            invalidate_base_agent,
            DynamicAgentWrapper,
            get_thread_config,
            _generate_dynamic_memory,
            FILE_OUTPUT_PROMPT,
        )
        assert callable(get_ops_agent)
        assert callable(create_base_agent)
        assert callable(get_thread_config)
        assert callable(invalidate_base_agent)
        assert len(FILE_OUTPUT_PROMPT) > 0

    def test_factory_imports(self):
        from app.deepagents.factory import create_agent_for_session
        assert callable(create_agent_for_session)

    def test_subagent_configs_imports(self):
        from app.deepagents.subagents.data_agent import DATA_AGENT_CONFIG
        from app.deepagents.subagents.analyze_agent import ANALYZE_AGENT_CONFIG
        from app.deepagents.subagents.execute_agent import EXECUTE_AGENT_CONFIG
        from app.deepagents.subagents.network_agent import NETWORK_AGENT_CONFIG
        from app.deepagents.subagents.storage_agent import STORAGE_AGENT_CONFIG
        from app.deepagents.subagents.security_agent import SECURITY_AGENT_CONFIG

        # 验证每个 subagent 都有必需字段
        for config in [
            DATA_AGENT_CONFIG, ANALYZE_AGENT_CONFIG, EXECUTE_AGENT_CONFIG,
            NETWORK_AGENT_CONFIG, STORAGE_AGENT_CONFIG, SECURITY_AGENT_CONFIG,
        ]:
            assert "name" in config, f"{config.get('name', '?')} 缺少 name"
            assert "description" in config, f"{config.get('name', '?')} 缺少 description"
            assert "tools" in config, f"{config.get('name', '?')} 缺少 tools"
            assert len(config["tools"]) > 0, f"{config['name']} 没有工具"

    def test_dynamic_permission_middleware_imports(self):
        from app.middleware.dynamic_permission_middleware import (
            DynamicPermissionMiddleware,
            BUILTIN_TOOLS,
        )
        assert callable(DynamicPermissionMiddleware)
        assert isinstance(BUILTIN_TOOLS, set)
        assert "write_todos" in BUILTIN_TOOLS
        assert "task" in BUILTIN_TOOLS

    def test_dynamic_approval_middleware_imports(self):
        from app.middleware.dynamic_approval_middleware import (
            DynamicApprovalMiddleware,
            BUILTIN_TOOLS,
        )
        assert callable(DynamicApprovalMiddleware)
        assert isinstance(BUILTIN_TOOLS, set)

    def test_alertmanager_client_imports(self):
        from app.integrations.alertmanager import (
            AlertManagerClient,
            get_alertmanager_client,
        )
        assert callable(AlertManagerClient)
        assert callable(get_alertmanager_client)

    def test_alert_tools_imports(self):
        from app.tools.alert_tools import (
            get_active_alerts,
            get_resolved_alerts,
            get_alert_statistics,
            silence_alert,
        )
        # 都是异步函数
        import asyncio
        assert asyncio.iscoroutinefunction(get_active_alerts)
        assert asyncio.iscoroutinefunction(get_resolved_alerts)
        assert asyncio.iscoroutinefunction(get_alert_statistics)
        assert asyncio.iscoroutinefunction(silence_alert)

    def test_middleware_init_no_message_trimming(self):
        """确认 MessageTrimmingMiddleware 已被移除"""
        from app.middleware import __all__ as middleware_all
        for name in middleware_all:
            assert "Trimming" not in name, f"MessageTrimmingMiddleware 未清理: {name}"

    def test_no_enhanced_services(self):
        """确认 enhanced_*_service 文件已删除"""
        import os
        app_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "services")
        for f in os.listdir(app_dir):
            assert "enhanced_" not in f, f"enhanced service 未清理: {f}"

    def test_no_embedding_dependencies(self):
        """确认无 embedding 残留"""
        from app.core.llm_factory import LLMFactory, get_llm
        assert not hasattr(LLMFactory, "create_embeddings"), "create_embeddings 未清理"

    def test_memory_manager_no_mem0_param(self):
        """确认 build_context 无 include_mem0 参数"""
        from app.memory.memory_manager import MemoryManager
        import inspect
        sig = inspect.signature(MemoryManager.build_context)
        assert "include_mem0" not in sig.parameters, "include_mem0 参数未清理"

    def test_no_embedding_constant(self):
        """确认 EMBEDDING_DIMENSION 已删除"""
        from app.core import constants
        assert not hasattr(constants, "EMBEDDING_DIMENSION"), "EMBEDDING_DIMENSION 未清理"

    def test_skills_files_exist(self):
        """确认 Skills 目录有内容"""
        import os
        project_root = os.path.dirname(os.path.dirname(__file__))
        skills_dir = os.path.join(project_root, "skills")
        assert os.path.isdir(skills_dir), "skills 目录不存在"

        expected_skills = [
            "k8s-troubleshooting",
            "pod-crashloop",
            "network-debugging",
            "resource-analysis",
            "incident-response",
        ]
        for skill in expected_skills:
            skill_path = os.path.join(skills_dir, skill, "SKILL.md")
            assert os.path.isfile(skill_path), f"缺少 skill: {skill}/SKILL.md"

    def test_component_cache_no_trimming(self):
        """确认 component_cache 不引用 MessageTrimmingMiddleware"""
        import app.deepagents.component_cache as cc
        import inspect
        src = inspect.getsource(cc)
        assert "MessageTrimmingMiddleware" not in src
        assert "message_trimming" not in src
