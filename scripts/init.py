#!/usr/bin/env python3
"""
Ops Agent 统一初始化脚本

整合所有初始化步骤，包括：
1. 创建数据库表
2. 初始化管理员账户和角色
3. 同步工具到审批配置
4. 初始化系统设置
5. 初始化提示词（静态数据）

运行方式：
    uv run python scripts/init.py              # 完整初始化
    uv run python scripts/init.py --skip-kb    # 跳过知识库初始化
    uv run python scripts/init.py --reset      # 重置数据库（危险操作）

提示词管理：
    - 初始化时：静态数据写入数据库
    - 运行时：从数据库动态加载（通过 UnifiedPromptOptimizer）
    - 管理界面：前端「提示词管理」页面可编辑
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine
from app.models.database import Base, SessionLocal
from app.models.user import User
from app.models.role import Role
from app.models.permission import Permission
from app.models.user_role import UserRole
from app.models.role_permission import RolePermission
from app.models.approval_config import ApprovalConfig
from app.models.system_setting import SystemSetting
from app.models.agent_prompt import AgentPrompt
from app.services.approval_config_service import ApprovalConfigService
from app.core.security import hash_password
from app.core.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ============================================================================
# 静态提示词数据（初始化时写入数据库，运行时从数据库加载）
# ============================================================================

DEFAULT_PROMPTS = [
    {
        "agent_name": "main-agent",
        "name": "主智能体",
        "description": "负责任务规划和委派的主智能体",
        "content": """你是一个智能运维助手。

你的职责：
1. 理解用户的问题和需求
2. 规划需要执行的任务
3. 委派给合适的子智能体执行
4. 汇总结果并生成报告

可用的子智能体：
- data-agent: 数据采集（K8s、Prometheus、Loki）
- analyze-agent: 分析诊断（问题根因分析）
- execute-agent: 执行操作（执行修复命令）
- network-agent: 网络诊断（Service、Ingress、DNS）
- security-agent: 安全巡检（RBAC、安全策略）
- storage-agent: 存储排查（PVC、PV、磁盘）

请根据用户的问题，选择合适的子智能体来完成任务。""",
    },
    {
        "agent_name": "data-agent",
        "name": "数据采集智能体",
        "description": "负责采集集群数据的智能体",
        "content": """你是一个数据采集智能体。

你的职责：
1. 从 Kubernetes 集群采集数据（Pod、Deployment、Service、Node 等）
2. 从 Prometheus 采集指标数据
3. 从 Loki 采集日志数据
4. 整理数据并返回给主智能体

可用工具：
- k8s_tools: K8s 资源查询（支持 SDK 和 CLI 降级）
- prometheus_tools: 指标查询
- loki_tools: 日志查询

请使用提供的工具采集相关数据，并整理成清晰的报告。""",
    },
    {
        "agent_name": "analyze-agent",
        "name": "分析诊断智能体",
        "description": "负责分析问题和诊断的智能体",
        "content": """你是一个分析诊断智能体。

你的职责：
1. 分析采集的数据
2. 识别问题根因
3. 提供诊断结论和建议

分析方法：
1. 检查 Pod 状态（Pending、CrashLoopBackOff、OOMKilled 等）
2. 检查资源使用（CPU、内存、磁盘）
3. 检查网络连通性（Service、Ingress、DNS）
4. 检查日志中的错误信息

请根据采集的数据进行分析和诊断，输出：
- root_cause: 根本原因
- severity: 严重程度（critical/high/medium/low）
- remediation_plan: 修复方案""",
    },
    {
        "agent_name": "execute-agent",
        "name": "执行操作智能体",
        "description": "负责执行修复操作的智能体",
        "content": """你是一个执行操作智能体。

你的职责：
1. 执行已批准的操作
2. 验证操作结果
3. 报告执行状态

可用工具：
- command_executor: 执行 Shell 命令
- k8s_tools: K8s 操作（重启、扩缩容、更新镜像等）

注意事项：
- 只执行用户已批准的操作
- 执行前再次确认操作参数
- 执行后验证结果
- 如有异常立即报告

请执行用户批准的操作，并报告执行结果。""",
    },
    {
        "agent_name": "network-agent",
        "name": "网络诊断智能体",
        "description": "负责网络连通性诊断的智能体",
        "content": """你是一个网络诊断智能体。

你的职责：
1. 诊断 Service 和 Ingress 配置问题
2. 排查 DNS 解析问题
3. 分析网络连通性
4. 检查端口和协议配置

诊断方法：
1. 检查 Service 的 ClusterIP、Port、TargetPort
2. 检查 Endpoints 是否正常
3. 检查 Ingress 规则和后端 Service
4. 检查 CoreDNS 配置
5. 测试网络连通性（ping、curl、nslookup）

请使用提供的工具诊断网络问题，并给出修复建议。""",
    },
    {
        "agent_name": "security-agent",
        "name": "安全巡检智能体",
        "description": "负责安全策略检查的智能体",
        "content": """你是一个安全巡检智能体。

你的职责：
1. RBAC 权限审计
2. 安全策略检查
3. 权限配置分析
4. 发现潜在安全风险

检查项目：
1. ServiceAccount 和 Token 挂载
2. Role/RoleBinding 权限范围
3. Pod 安全策略（SecurityContext）
4. NetworkPolicy 配置
5. 敏感信息（Secret、ConfigMap）

请使用提供的工具进行安全检查，并输出安全报告。""",
    },
    {
        "agent_name": "storage-agent",
        "name": "存储排查智能体",
        "description": "负责存储问题排查的智能体",
        "content": """你是一个存储排查智能体。

你的职责：
1. PVC/PV 问题诊断
2. 磁盘空间分析
3. 存储性能检查
4. 存储类配置检查

诊断方法：
1. 检查 PVC 状态（Pending、Bound、Lost）
2. 检查 PV 容量和可用空间
3. 检查 StorageClass 配置
4. 检查 Node 磁盘使用率
5. 检查 Pod 挂载点

常见问题：
- PVC Pending：StorageClass 不存在、配额不足
- 磁盘满：清理日志、扩容 PV
- IO 性能：检查存储后端状态

请使用提供的工具排查存储问题。""",
    },
]


# ============================================================================
# 系统设置静态数据
# ============================================================================

DEFAULT_SYSTEM_SETTINGS = [
    # 应用基础配置
    {"key": "app_name", "value": "Ops Agent", "description": "应用名称", "category": "app"},
    {"key": "app_version", "value": "4.0.0", "description": "应用版本", "category": "app"},
    {"key": "default_llm_provider", "value": "deepseek", "description": "默认 LLM 提供商", "category": "llm"},
    {"key": "max_chat_history", "value": "50", "description": "最大聊天历史记录数", "category": "app"},
    {"key": "enable_approval", "value": "true", "description": "是否启用审批流程", "category": "app"},
    # 飞书配置
    {"key": "feishu.chat_mode", "value": "ai_chat", "description": "飞书聊天模式", "category": "feishu"},
    {"key": "feishu.connection_mode", "value": "auto", "description": "飞书连接模式", "category": "feishu"},
    # 功能开关
    {"key": "features.v2_inspection_enabled", "value": "true", "description": "启用 V2 巡检", "category": "features"},
    {"key": "features.v2_healing_enabled", "value": "true", "description": "启用 V2 自愈", "category": "features"},
    {"key": "features.v2_security_enabled", "value": "true", "description": "启用 V2 安全审核", "category": "features"},
]


# ============================================================================
# 初始化函数
# ============================================================================

def create_tables(reset: bool = False):
    """创建所有数据库表"""
    logger.info("=" * 60)
    logger.info("📦 步骤 1: 创建数据库表")
    logger.info("=" * 60)

    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL)

    if reset:
        logger.warning("⚠️  重置模式：将删除所有现有表！")
        Base.metadata.drop_all(engine)
        logger.info("  ✅ 已删除所有旧表")

    Base.metadata.create_all(engine)
    logger.info("✅ 数据库表创建完成")


def init_admin_user():
    """初始化管理员用户和角色"""
    logger.info("=" * 60)
    logger.info("👤 步骤 2: 初始化管理员用户")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        settings = get_settings()

        # 检查管理员是否存在
        admin = db.query(User).filter(User.username == settings.INITIAL_ADMIN_USERNAME).first()
        if admin:
            logger.info(f"  管理员用户已存在: {admin.username}")
        else:
            admin = User(
                username=settings.INITIAL_ADMIN_USERNAME,
                email=settings.INITIAL_ADMIN_EMAIL,
                hashed_password=hash_password(settings.INITIAL_ADMIN_PASSWORD),
                is_superuser=True,
                is_active=True,
            )
            db.add(admin)
            db.commit()
            logger.info(f"  ✅ 创建管理员用户: {admin.username}")

        # 检查管理员角色
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        if not admin_role:
            admin_role = Role(name="admin", description="管理员角色，拥有所有权限")
            db.add(admin_role)
            db.commit()
            logger.info("  ✅ 创建管理员角色: admin")

        # 检查权限
        admin_perm = db.query(Permission).filter(Permission.code == "admin").first()
        if not admin_perm:
            admin_perm = Permission(
                code="admin",
                name="管理员权限",
                description="拥有所有权限"
            )
            db.add(admin_perm)
            db.commit()
            logger.info("  ✅ 创建管理员权限: admin")

        # 分配角色和权限
        if admin and admin_role and admin_perm:
            user_role = db.query(UserRole).filter(
                UserRole.user_id == admin.id,
                UserRole.role_id == admin_role.id
            ).first()
            if not user_role:
                user_role = UserRole(user_id=admin.id, role_id=admin_role.id)
                db.add(user_role)
                db.commit()
                logger.info(f"  ✅ 分配管理员角色: {admin_role.name}")

            role_perm = db.query(RolePermission).filter(
                RolePermission.role_id == admin_role.id,
                RolePermission.permission_id == admin_perm.id
            ).first()
            if not role_perm:
                role_perm = RolePermission(
                    role_id=admin_role.id,
                    permission_id=admin_perm.id
                )
                db.add(role_perm)
                db.commit()
                logger.info(f"  ✅ 分配管理员权限: {admin_perm.code}")

        logger.info("✅ 管理员用户初始化完成")

    except Exception as e:
        logger.error(f"❌ 初始化管理员用户失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def sync_tools_and_approval():
    """同步工具到审批配置表"""
    logger.info("=" * 60)
    logger.info("🔧 步骤 3: 同步工具到审批配置表")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        synced_count = ApprovalConfigService.sync_tools_to_db(db)
        logger.info(f"  ✅ 同步了 {synced_count} 个新工具")

        total_count = db.query(ApprovalConfig).count()
        logger.info(f"  📊 总工具数: {total_count}")

        logger.info("✅ 工具同步完成")

    except Exception as e:
        logger.error(f"❌ 同步工具失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def init_system_settings():
    """初始化系统设置"""
    logger.info("=" * 60)
    logger.info("⚙️  步骤 4: 初始化系统设置")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        created_count = 0
        skipped_count = 0

        for setting in DEFAULT_SYSTEM_SETTINGS:
            existing = db.query(SystemSetting).filter(SystemSetting.key == setting["key"]).first()
            if not existing:
                new_setting = SystemSetting(
                    key=setting["key"],
                    value=setting["value"],
                    description=setting.get("description", ""),
                    category=setting.get("category", "general"),
                )
                db.add(new_setting)
                created_count += 1
                logger.info(f"  ✅ 创建系统设置: {setting['key']}")
            else:
                skipped_count += 1

        db.commit()
        logger.info(f"✅ 系统设置初始化完成 (创建 {created_count}, 跳过 {skipped_count})")

    except Exception as e:
        logger.error(f"❌ 初始化系统设置失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def seed_default_prompts():
    """初始化默认提示词（静态数据写入数据库）"""
    logger.info("=" * 60)
    logger.info("📝 步骤 5: 初始化默认提示词")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        created_count = 0
        skipped_count = 0

        for prompt_data in DEFAULT_PROMPTS:
            existing = db.query(AgentPrompt).filter(
                AgentPrompt.agent_name == prompt_data["agent_name"]
            ).first()
            if not existing:
                prompt = AgentPrompt(
                    agent_name=prompt_data["agent_name"],
                    name=prompt_data["name"],
                    description=prompt_data["description"],
                    content=prompt_data["content"],
                    version=1,
                    is_active=True
                )
                db.add(prompt)
                created_count += 1
                logger.info(f"  ✅ 创建提示词: {prompt_data['agent_name']}")
            else:
                skipped_count += 1
                logger.info(f"  ⏭️  提示词已存在: {prompt_data['agent_name']}")

        db.commit()
        logger.info(f"✅ 默认提示词初始化完成 (创建 {created_count}, 跳过 {skipped_count})")

    except Exception as e:
        logger.error(f"❌ 初始化提示词失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def init_knowledge_base():
    """初始化知识库（可选）"""
    logger.info("=" * 60)
    logger.info("📚 步骤 6: 初始化知识库（可选）")
    logger.info("=" * 60)

    try:
        from init_vector_knowledge import init_vector_knowledge as init_kb
        init_kb()
        logger.info("✅ 知识库初始化完成")
    except ImportError:
        logger.warning("⚠️  知识库初始化脚本不存在，跳过")
    except Exception as e:
        logger.warning(f"⚠️  知识库初始化失败: {e}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Ops Agent 统一初始化脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  uv run python scripts/init.py              # 完整初始化
  uv run python scripts/init.py --skip-kb    # 跳过知识库
  uv run python scripts/init.py --reset      # 重置数据库
        """
    )
    parser.add_argument("--skip-kb", action="store_true", help="跳过知识库初始化")
    parser.add_argument("--reset", action="store_true", help="重置数据库（删除所有表后重建）")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("🚀 Ops Agent 统一初始化")
    logger.info("=" * 60)
    logger.info(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"  模式: {'重置' if args.reset else '初始化'}")
    logger.info("")

    try:
        # 步骤 1: 创建数据库表
        create_tables(reset=args.reset)

        # 步骤 2: 初始化管理员用户
        init_admin_user()

        # 步骤 3: 同步工具到审批配置表
        sync_tools_and_approval()

        # 步骤 4: 初始化系统设置
        init_system_settings()

        # 步骤 5: 初始化默认提示词
        seed_default_prompts()

        # 可选: 步骤 6: 初始化知识库
        if not args.skip_kb:
            logger.info("")
            init_knowledge_base()

        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ 初始化完成！")
        logger.info("=" * 60)
        logger.info("")
        logger.info("下一步：")
        logger.info("  1. 启动服务: uv run uvicorn app.main:app --reload")
        logger.info("  2. 访问 API 文档: http://localhost:8000/docs")
        logger.info("  3. 访问 Web UI: http://localhost:5173")
        logger.info(f"  4. 默认账号: {get_settings().INITIAL_ADMIN_USERNAME} / {get_settings().INITIAL_ADMIN_PASSWORD}")
        logger.info("")

    except Exception as e:
        logger.error(f"❌ 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
