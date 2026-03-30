---
description: K8s 事件响应流程：事件分级、响应步骤、升级策略、通知模板
---

# K8s 事件响应流程

## 事件分级

| 级别 | 定义 | 响应时间 | 示例 |
|------|------|----------|------|
| P0 | 核心服务完全不可用 | 5 分钟内 | 数据库宕机、核心 API 全挂 |
| P1 | 核心服务部分不可用 | 15 分钟内 | 部分节点 NotReady、Service 大量 5xx |
| P2 | 非核心服务受影响 | 1 小时内 | 监控系统异常、日志采集中断 |
| P3 | 潜在风险 | 下个工作日 | 磁盘使用率 > 80%、证书即将过期 |

## 响应流程

### Step 1: 确认和评估（5 分钟内）
```
# 确认告警是否真实
kubectl get nodes
kubectl get pods -A | grep -v Running
kubectl get events -A --sort-by='.lastTimestamp' | tail -50
```

- 确认影响范围（哪些服务、哪些用户）
- 确认事件级别
- 通知相关责任人

### Step 2: 止血和隔离
```
# P0/P1: 优先止血
# - 扩容：kubectl scale deployment <name> --replicas=N
# - 回滚：kubectl rollout undo deployment/<name>
# - 摘流：修改 Ingress 或 Service 权重
# - 隔离：kubectl cordon <node>（隔离故障节点）
```

### Step 3: 根因分析
- 查看 Events（`kubectl get events -A`）
- 查看日志（`kubectl logs`、Loki）
- 查看指标（Prometheus/Grafana）
- 对比变更记录（最近部署、配置变更）

### Step 4: 修复和验证
- 执行修复操作
- 验证服务恢复（健康检查 + 业务验证）
- 观察 5-10 分钟确认稳定

### Step 5: 复盘和记录
- 编写故障报告
- 更新 Runbook
- 提交改进项

## 升级策略

### P0 升级链
1. 值班工程师 → 2. 研发负责人 → 3. 技术总监

### P1 升级链
1. 值班工程师 → 2. 研发负责人

### P2/P3
值班工程师自行处理，必要时升级

## 常见 P0 场景快速止血

### 全集群 Pod 异常
```
# 检查 API Server
kubectl get cs

# 检查 etcd
kubectl get pods -n kube-system | grep etcd

# 检查网络插件
kubectl get pods -n kube-system | grep -E "calico|flannel|cilium|kube-proxy"
```

### 数据库连接耗尽
```
# 检查连接数
kubectl exec -it <pod-name> -- mysql -u root -p -e "SHOW PROCESSLIST;"

# 重启应用 Pod 释放连接
kubectl rollout restart deployment/<name> -n <namespace>
```

### 磁盘满
```
# 查看磁盘使用
df -h

# 清理
docker system prune -a --volumes
kubectl delete pod --field-selector=status.phase=Succeeded -A
```

## 通知模板

### P0 通知
```
🔴 【P0 紧急告警】
服务: <service-name>
现象: <symptom>
影响: <impact>
当前状态: <status>
正在处理: <action>
```

### 恢复通知
```
✅ 【故障恢复】
服务: <service-name>
故障时长: <duration>
根因: <root-cause>
修复方式: <fix>
后续改进: <improvement>
```
