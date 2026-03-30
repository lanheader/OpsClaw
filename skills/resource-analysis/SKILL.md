---
description: K8s 资源使用分析：CPU/内存/磁盘使用率、资源浪费识别、HPA 配置建议
---

# K8s 资源使用分析

## 适用场景
- Node CPU/内存/磁盘使用率高
- Pod 资源使用异常（CPU Throttling、OOM）
- 需要识别资源浪费（request/limit 配置不合理）
- HPA 配置优化
- 成本优化

## 分析流程

### Step 1: 集群资源概览
```
# Node 资源使用
kubectl top nodes

# Pod 资源使用（按 CPU 排序）
kubectl top pods -A --sort-by=cpu | head -20

# Pod 资源使用（按内存排序）
kubectl top pods -A --sort-by=memory | head -20
```

### Step 2: 资源瓶颈分析

#### CPU 瓶颈
```
# 查看 CPU 使用率超过 80% 的 Pod
kubectl top pods -A --no-headers | awk '$2+0 > 80 {print}'

# 检查 CPU Throttling（cgroup throttle 信息）
kubectl exec <pod-name> -n <namespace> -- cat /sys/fs/cgroup/cpu.stat 2>/dev/null || \
kubectl exec <pod-name> -n <namespace> -- cat /sys/fs/cgroup/cpu/cpu.cfs_throttled_periods
```

#### 内存瓶颈
```
# 查看内存使用率超过 80% 的 Pod
kubectl top pods -A --no-headers | awk '$3+0 > 80 {print}'

# 检查 Pod 的 OOM 状态
kubectl describe pod <pod-name> -n <namespace> | grep -i oom
```

#### 磁盘瓶颈
```
# Node 磁盘使用
df -h
du -sh /var/lib/docker/* 2>/dev/null | sort -rh | head -10
du -sh /var/lib/kubelet/* 2>/dev/null | sort -rh | head -10

# 清理未使用的镜像
crictl rmi --prune
```

### Step 3: 资源配置合理性检查

#### 检查 request/limit 比率
```
# 找出 request 和 limit 差距过大的 Pod
kubectl get pods -A -o json | jq -r '
  .items[] | select(.spec.containers[].resources) |
  "\(.metadata.namespace)/\(.metadata.name)" as $pod |
  .spec.containers[] | select(.resources.requests and .resources.limits) |
  "\($pod) \(.name) req=\(.resources.requests.cpu // "none")/\(.resources.requests.memory // "none") lim=\(.resources.limits.cpu // "none")/\(.resources.limits.memory // "none")"
'
```

#### 检查未设置 request/limit 的 Pod
```
kubectl get pods -A -o json | jq -r '
  .items[] |
  "\(.metadata.namespace)/\(.metadata.name)" as $pod |
  .spec.containers[] |
  select(.resources.requests == null or .resources.limits == null) |
  "\($pod) \(.name) missing requests or limits"
'
```

### Step 4: HPA 分析
```
# 查看 HPA 状态
kubectl get hpa -A

# 查看 HPA 详细事件
kubectl describe hpa <hpa-name> -n <namespace>
```

#### HPA 优化建议
- `targetCPUUtilizationPercentage`：建议 70-80%（过低浪费资源，过高容易频繁扩缩）
- `minReplicas`：至少 2（保证高可用）
- `behavior.scaleDown.stabilizationWindowSeconds`：建议 300-600s（避免频繁缩容）
- `behavior.scaleUp stabilizationWindowSeconds`：建议 60-120s

### Step 5: 资源浪费识别

#### 内存浪费
```
# 找出 request 是实际使用 2 倍以上的 Pod
for pod in $(kubectl top pods -A --no-headers | awk '{print $1"/"$2}'); do
  ns=${pod%%/*}; name=${pod#*/}
  request=$(kubectl get pod $name -n $ns -o jsonpath='{.spec.containers[0].resources.requests.memory}' 2>/dev/null)
  actual=$(kubectl top pod $name -n $ns --no-headers | awk '{print $3}' | tr -d '%MiGi')
  echo "$pod: request=$request actual=${actual}Mi"
done
```

## 常见问题

### CPU Throttling
- **症状**：应用延迟升高，但 CPU 使用率不高
- **原因**：CPU limit 过低，cgroup 限流
- **修复**：提高 CPU limit，或优化应用性能

### OOMKilled
- **症状**：Pod 被 kubelet 杀死，Exit Code 137
- **原因**：内存使用超过 limit
- **修复**：增加 memory limit 或优化应用内存

### 资源碎片
- **症状**：Node 有剩余资源但 Pod 调度不上去
- **原因**：requests 和 limits 差距大，或存在大量小 request 的 Pod
- **修复**：合理设置 requests = 实际使用的 80-90%
