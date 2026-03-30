---
description: Pod CrashLoopBackOff 标准排查路径，覆盖 5 种常见原因
---

# Pod CrashLoopBackOff 排查

## 适用场景
Pod 状态为 CrashLoopBackOff 或频繁 Restart（RestartCount 持续增长）

## 排查流程

### Step 1: 获取 Pod 状态和事件
```
kubectl describe pod <pod-name> -n <namespace>
kubectl get events --field-selector involvedObject.name=<pod-name> -n <namespace>
```

关键信息：
- `Last State` 中的 Exit Code
- Events 中的 `Back-off restarting failed container`
- `Containers` 中的 `State.Terminated.Reason`

### Step 2: 查看容器日志
```
kubectl logs <pod-name> -n <namespace> --previous
```
如果日志为空，可能是启动阶段就崩了（检查 Init Container 或 entrypoint）。

### Step 3: 根据日志/Exit Code 定位原因

#### 原因 1: 应用启动失败（最常见，Exit Code 1）
- **症状**：日志显示 "Connection refused"、"Failed to connect to xxx"、"Timeout"
- **根因**：依赖服务未就绪、配置错误、端口冲突
- **排查**：
  ```
  # 检查依赖服务状态
  kubectl get pods -n <dependency-namespace>
  # 检查 Service 端点
  kubectl get endpoints <service-name> -n <namespace>
  # 在 Pod 内测试连通性
  kubectl exec -it <pod-name> -n <namespace> -- curl -s <service>:<port>
  ```
- **修复**：修复依赖服务，或调整启动顺序（加 init container 等待依赖就绪）

#### 原因 2: 配置错误（Exit Code 1）
- **症状**：日志显示 "config file not found"、"invalid config"、"key not found"
- **根因**：ConfigMap/Secret 未挂载、内容格式错误、环境变量缺失
- **排查**：
  ```
  # 检查 ConfigMap/Secret 是否存在
  kubectl get configmap -n <namespace>
  kubectl get secret -n <namespace>
  # 检查挂载情况
  kubectl describe pod <pod-name> -n <namespace> | grep -A5 "Mounts\|Volumes\|Environment"
  ```
- **修复**：创建/更新 ConfigMap/Secret，或修正 volumeMounts 路径

#### 原因 3: 资源不足 OOMKilled（Exit Code 137）
- **症状**：Events 显示 `OOMKilled`，Last State 中 `Exit Code 137`，`Reason: OOMKilled`
- **根因**：应用内存使用超过 limits
- **排查**：
  ```
  # 确认 OOMKilled
  kubectl describe pod <pod-name> -n <namespace> | grep -i oom
  # 查看实际内存使用
  kubectl top pod <pod-name> -n <namespace>
  # 查看容器 limits
  kubectl get pod <pod-name> -n <namespace> -o jsonpath='{.spec.containers[*].resources}'
  ```
- **修复**：增加 `resources.limits.memory`，或优化应用内存使用

#### 原因 4: 镜像问题
- **症状**：Events 显示 `ImagePullBackOff` 或 `ErrImagePull`
- **根因**：镜像名/tag 错误、仓库不可达、凭证缺失
- **排查**：
  ```
  kubectl describe pod <pod-name> -n <namespace> | grep -i image
  kubectl get events -n <namespace> | grep -i image
  ```
- **修复**：修正镜像配置，添加 `imagePullSecrets`

#### 原因 5: 健康检查失败（Exit Code 137 或 143）
- **症状**：Events 显示 `Liveness probe failed`，Pod 被 kubelet 重启
- **根因**：livenessProbe 配置不合理（超时太短、路径错误、应用启动慢）
- **排查**：
  ```
  kubectl describe pod <pod-name> -n <namespace> | grep -A10 "Liveness\|Readiness"
  ```
- **修复**：调整探针参数：
  - `initialDelaySeconds`：增加启动等待时间
  - `timeoutSeconds`：增加超时
  - `failureThreshold`：增加失败容忍次数
  - `periodSeconds`：增加检查间隔

### Step 4: 验证修复
```
kubectl get pod <pod-name> -n <namespace> -w
kubectl logs <pod-name> -n <namespace> -f
```

## 快速诊断命令
```bash
# 一键诊断 CrashLoopBackOff Pod
kubectl get pods -A | grep CrashLoopBackOff | awk '{print $1, $2}' | while read ns pod; do
  echo "=== $ns/$pod ==="
  kubectl describe pod $pod -n $ns | grep -E "Exit Code|Reason|OOMKilled|Image:"
  kubectl logs $pod -n $ns --previous 2>&1 | tail -5
  echo
done
```
