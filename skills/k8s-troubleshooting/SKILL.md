---
description: K8s 通用故障排查框架，覆盖 Node NotReady、Pod Pending、Service 无端点等常见问题
---

# K8s 通用故障排查

## 适用场景
- Node 状态异常（NotReady、OutOfDisk、MemoryPressure）
- Pod 状态异常（Pending、Unknown、ImagePullBackOff）
- Service 无法访问
- Deployment 更新异常（进度卡住、回滚失败）
- ReplicaSet 副本数不符预期

## 通用排查流程

### Step 1: 确认问题范围
```
kubectl get nodes
kubectl get pods -A -o wide | grep -v Running
kubectl get events -A --sort-by='.lastTimestamp' | tail -30
```

### Step 2: 检查资源状态
```
# 查看资源详情
kubectl describe <resource> <name> -n <namespace>

# 查看事件（最关键的信息来源）
kubectl get events -n <namespace> --sort-by='.lastTimestamp'

# 查看资源 YAML（确认配置是否正确）
kubectl get <resource> <name> -n <namespace> -o yaml
```

### Step 3: 查看日志
```
# Pod 日志
kubectl logs <pod-name> -n <namespace> --previous
kubectl logs <pod-name> -n <namespace> -f --tail=100

# 多容器 Pod
kubectl logs <pod-name> -c <container-name> -n <namespace>

# Init 容器日志
kubectl logs <pod-name> -c <init-container-name> -n <namespace>
```

### Step 4: 检查资源配额和限制
```
kubectl describe resourcequota -n <namespace>
kubectl describe limitrange -n <namespace>
kubectl top nodes
kubectl top pods -n <namespace>
```

## 常见问题模式

### Node NotReady
- 检查 kubelet 状态：`systemctl status kubelet`
- 检查节点事件：`kubectl describe node <node-name>`
- 常见原因：kubelet 挂了、磁盘满、网络断开、证书过期

### Pod Pending
- 检查 Events：`kubectl describe pod <pod-name>`
- 常见原因：
  - 资源不足（Insufficient cpu/memory）：扩容 Node 或降低 request
  - NodeSelector 无匹配 Node：检查 label
  - PVC 未绑定：`kubectl get pvc`
  - Taint/Toleration 不匹配：`kubectl describe node` 查看 taints

### ImagePullBackOff / ErrImagePull
- 检查镜像名和 tag 是否正确
- 检查镜像仓库凭证：`kubectl get secret`
- 手动拉取测试：`docker pull <image>`
- 检查网络连通性到镜像仓库

### Deployment 进度卡住
```
kubectl rollout status deployment/<name> -n <namespace>
kubectl describe deployment/<name> -n <namespace>
```
- 常见原因：新版本 Pod 启动失败、资源不足、 readinessProbe 配置问题

### Service 无端点
```
kubectl get endpoints <service-name> -n <namespace>
kubectl describe service <service-name> -n <namespace>
```
- 检查 selector 是否匹配 Pod labels
- 检查 Pod 是否处于 Running 状态

## 修复建议模板
1. 确认根因（用 kubectl describe/events/logs 验证）
2. 制定修复方案（优先非破坏性操作）
3. 执行修复
4. 验证恢复（`kubectl get` + 应用层面验证）
5. 记录经验（写 runbook）
