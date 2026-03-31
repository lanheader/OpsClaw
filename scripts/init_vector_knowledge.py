"""
初始化向量知识库数据

将运维文档和故障案例导入知识库
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.memory.memory_manager import get_memory_manager


async def init_knowledge_base():
    """初始化知识库"""
    mm = get_memory_manager()

    print("=" * 60)
    print("初始化向量知识库")
    print("=" * 60)

    # 运维最佳实践
    knowledge_items = [
        {
            "title": "K8s Pod 重启最佳实践",
            "content": """Kubernetes Pod 重启最佳实践：

1. 诊断优先：
   - 先查看 Pod 状态和事件（kubectl describe pod）
   - 检查日志找出重启原因
   - 分析资源使用情况

2. 常见重启原因：
   - OOMKilled: 内存限制太低
   - CrashLoopBackOff: 应用启动失败
   - ImagePullBackOff: 镜像拉取失败

3. 处理步骤：
   - 查看 Pod 描述：kubectl describe pod <pod-name>
   - 查看日志：kubectl logs <pod-name> --previous
   - 查看事件：kubectl get events --sort-by='.metadata.creationTimestamp'

4. 预防措施：
   - 设置合理的资源限制
   - 配置健康检查
   - 使用多副本部署
""",
            "category": "kubernetes",
            "tags": ["k8s", "pod", "restart", "最佳实践"],
            "source": "运维手册"
        },
        {
            "title": "Redis 内存问题排查指南",
            "content": """Redis 内存问题排查指南：

1. 内存占用分析：
   - 连接 Redis 执行 INFO memory
   - 查看 used_memory 和 maxmemory
   - 检查内存使用率

2. 常见内存问题：
   - 大键问题：单个 key 占用过多内存
   - 键过期策略未配置
   - 持久化文件过大
   - 客户端连接数过多

3. 解决方案：
   - 使用 MEMORY USAGE 命令查看每个 key 的内存占用
   - 删除或清理大键：UNLINK 或 DEL
   - 设置键过期时间：EXPIRE key seconds
   - 配置 maxmemory-policy volatile-lru

4. 监控建议：
   - 监控内存使用率 > 80%
   - 监控键数量和过期比例
   - 监控持久化文件大小
""",
            "category": "database",
            "tags": ["redis", "memory", "troubleshooting"],
            "source": "运维手册"
        },
        {
            "title": "数据库连接池耗尽处理",
            "content": """数据库连接池耗尽问题处理：

1. 问题现象：
   - 应用报错 "Pool exhausted"
   - 响应时间变慢
   - 数据库连接数达到上限

2. 常见原因：
   - 连接未正确关闭（连接泄漏）
   - 连接池配置不当（太小或无限增长）
   - 长事务占用连接
   - 应用重启后连接未释放

3. 解决方案：
   - 检查代码确保连接在 finally 块中关闭
   - 配置合理的连接池大小（通常 2-4 倍 CPU 核心数）
   - 设置连接超时时间
   - 配置空闲连接超时清理
   - 使用连接池监控

4. 配置示例：
   - 最小连接数：10
   - 最大连接数：100
   - 连接超时：30 秒
   - 空闲超时：600 秒
   - 最大生命周期：30 分钟

5. 预防措施：
   - 代码审查确保正确关闭连接
   - 使用连接池监控
   - 配置告警（连接数 > 80%）
""",
            "category": "database",
            "tags": ["database", "connection", "pool", "troubleshooting"],
            "source": "运维手册"
        },
        {
            "title": "Nginx 高并发配置优化",
            "content": """Nginx 高并发配置优化指南：

1. 核心配置参数：
   worker_processes: 设置为 CPU 核心数
   worker_connections: 提高到 10240 或更高
   keepalive_timeout: 65
   keepalive_requests: 100

2. 缓冲区优化：
   client_body_buffer_size: 128k
   client_header_buffer_size: 1k
   large_client_header_buffers: 4 16k
   client_max_body_size: 100m

3. 操作系统优化：
   fs.file-max = 655350
   net.ipv4.tcp_tw_reuse = 1
   net.ipv4.tcp_fin_timeout = 30
   net.core.somaxconn = 4096

4. 日志优化：
   access_log_buffer=16k
   access_log_buffer_size=32k
   关闭或优化错误日志记录

5. 性能监控：
   - 监控活跃连接数
   - 监控请求响应时间
   - 监控 5xx 错误率
   - 使用 Nginx ampliv 模块监控
""",
            "category": "service",
            "tags": ["nginx", "performance", "optimization"],
            "source": "运维手册"
        },
        {
            "title": "应用健康检查配置指南",
            "content": """K8s 应用健康检查配置指南：

1. 探针类型：
   - livenessProbe: 存活探针（检测应用是否存活）
   - readinessProbe: 就绪探针（检测应用是否准备好接收流量）
   - startupProbe: 启动探针（检测应用是否启动成功）

2. 配置参数：
   initialDelaySeconds: 容器启动后延迟多少秒开始探测
   periodSeconds: 探测间隔（秒）
   timeoutSeconds: 探测超时时间（秒）
   successThreshold: 连续成功多少次才算成功
   failureThreshold: 连续失败多少次才算失败

3. 配置建议：
   - HTTP 探针：使用 /health 或 /readiness 端点
   - TCP 探针：适用于 TCP 服务
   - Exec 探针：执行命令检查（不推荐）

4. 最佳实践：
   - initialDelaySeconds: 30-60 秒（给应用足够的启动时间）
   - periodSeconds: 10 秒
   - timeoutSeconds: 5 秒
   - failureThreshold: 3 次
   - 对于 Java 应用，initialDelaySeconds 应更长

5. 注意事项：
   - 健康检查端点应该轻量快速
   - 避免健康检查触发复杂逻辑
   - 探针超时应该小于周期时间
""",
            "category": "kubernetes",
            "tags": ["k8s", "health", "probe", "配置"],
            "source": "运维手册"
        }
    ]

    # 故障案例
    incident_items = [
        {
            "title": "Pod 频繁重启 - 健康检查配置问题",
            "content": """故障现象：Deployment 中的 Pod 出现频繁重启，状态为 CrashLoopBackOff

故障分析：
- Pod 重启次数超过 50 次
- 应用日志显示启动正常
- kubectl describe pod 显示 Liveness probe failed

根本原因：
健康检查探针超时时间太短（3 秒），而应用启动需要 5 秒才能响应健康检查。

解决方案：
1. 调整 livenessProbe.initialDelaySeconds 从 10 秒增加到 30 秒
2. 调整 timeoutSeconds 从 3 秒增加到 10 秒
3. 验证配置后重新部署

结果：Pod 稳定运行，不再重启
""",
            "incident_type": "kubernetes",
            "root_cause": "健康检查配置不当"
        },
        {
            "title": "Redis 内存使用率达到 95%",
            "content": """故障现象：Redis 内存使用率达到 95%，开始驱逐数据

故障分析：
- 使用 Redis INFO memory 发现内存占用高
- 使用 --bigkeys 命令发现几个大键占用大量内存
- 查看日志发现没有设置过期时间的键

根本原因：
缓存数据未设置过期时间，数据持续累积

解决方案：
1. 使用 SCAN 命令扫描大键
2. 对不需要的数据设置过期时间：EXPIRE key 3600
3. 配置 maxmemory-policy 为 volatile-lru
4. 监控内存使用率

结果：内存使用率下降到 60%，系统稳定
""",
            "incident_type": "database",
            "root_cause": "键过期策略未配置"
        },
        {
            "title": "数据库连接池耗尽",
            "content": """故障现象：应用报错 "Pool exhausted"，无法获取数据库连接

故障分析：
- 数据库连接数达到上限
- 应用日志显示大量连接未释放
- 通过代码审查发现部分代码未关闭连接

根本原因：
代码中存在连接泄漏，连接未在 finally 块中正确关闭

解决方案：
1. 紧急处理：重启应用释放连接
2. 修复代码：确保所有连接在 finally 块中关闭
3. 增加连接池配置：从 50 增加到 100
4. 配置连接超时和空闲超时
5. 添加连接池监控

结果：问题解决，连接池使用率稳定在 60%
""",
            "incident_type": "database",
            "root_cause": "连接泄漏"
        },
        {
            "title": "Nginx 502 Gateway Error",
            "content": """故障现象：用户访问服务时出现 502 Gateway Error

故障分析：
- Nginx 日志显示 "upstream prematurely closed connection"
- 后端服务日志显示连接数过多
- 检查发现后端服务连接池配置不当

根本原因：
后端服务连接池耗尽，无法接受新连接

解决方案：
1. 紧急扩容：增加后端服务实例
2. 优化 Nginx 配置：
   - 增加 proxy_connect_timeout
   - 增加 proxy_send_timeout
   - 增加 proxy_read_timeout
3. 优化后端服务连接池配置
4. 配置健康检查剔除不健康的后端

结果：服务恢复正常
""",
            "incident_type": "service",
            "root_cause": "后端连接池耗尽"
        }
    ]

    # 导入知识
    print("\n📚 导入知识库...")
    for i, item in enumerate(knowledge_items, 1):
        try:
            memory_id = await mm.learn_knowledge(
                title=item["title"],
                content=item["content"],
                category=item["category"],
                tags=item["tags"],
                source=item["source"]
            )
            print(f"  [{i}] {item['title']} (ID: {memory_id})")
        except Exception as e:
            print(f"  [{i}] 导入失败: {item['title']} - {e}")

    # 导入故障案例
    print("\n📝 导入故障案例...")
    for i, item in enumerate(incident_items, 1):
        try:
            memory_id = await mm.remember_incident(
                content=item["content"],
                incident_type=item["incident_type"],
                title=item["title"],
                root_cause=item["root_cause"]
            )
            print(f"  [{i}] {item['title']} (ID: {memory_id})")
        except Exception as e:
            print(f"  [{i}] 导入失败: {item['title']} - {e}")

    # 显示统计
    print("\n📊 知识库统计:")
    stats = await mm.get_stats()
    print(f"  故障记忆: {stats['vector_store']['incident_memories']} 条")
    print(f"  知识库: {stats['vector_store']['knowledge_memories']} 条")
    print(f"  会话记忆: {stats['vector_store']['session_memories']} 条")

    print("\n✅ 知识库初始化完成")


if __name__ == "__main__":
    asyncio.run(init_knowledge_base())
