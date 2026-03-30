---
description: K8s 网络问题排查：DNS解析、Service互通、Ingress配置、网络策略
---

# K8s 网络问题排查

## 适用场景
- DNS 解析失败（域名无法解析）
- Service 间调用超时或拒绝连接
- Ingress 返回 404/502/503
- 跨 Namespace 通信失败
- 网络策略导致通信阻断

## 排查流程

### Step 1: 确认问题现象
```
# 检查 Service 端点
kubectl get endpoints -A

# 检查 Ingress 状态
kubectl get ingress -A

# 检查网络策略
kubectl get networkpolicy -A
```

### Step 2: DNS 问题排查

#### 检查 CoreDNS 状态
```
kubectl get pods -n kube-system -l k8s-app=kube-dns
kubectl logs -n kube-system -l k8s-app=kube-dns --tail=50
```

#### 测试 DNS 解析
```
# 进入测试 Pod
kubectl run dns-test --image=busybox:1.36 --rm -it --restart=Never -- nslookup kubernetes.default

# 测试跨 Namespace 服务解析
kubectl run dns-test --image=busybox:1.36 --rm -it --restart=Never -- nslookup <service-name>.<namespace>.svc.cluster.local
```

#### 常见 DNS 问题
- **CoreDNS Pod 不健康**：检查资源限制、节点状态
- **Pod 的 dnsPolicy 配置错误**：默认应使用 `ClusterFirst`
- **自定义 dnsConfig 冲突**：检查 Pod 的 dnsConfig 配置
- **ndots 配置问题**：搜索域名时 "." 数量导致解析路径不同

### Step 3: Service 互通问题

#### 检查 Service 配置
```
kubectl describe svc <service-name> -n <namespace>
```
确认：
- `Selector` 是否匹配目标 Pod 的 labels
- `Port` 和 `TargetPort` 是否正确
- `Type` 是否符合预期（ClusterIP/NodePort/LoadBalancer）

#### 检查 Endpoints
```
kubectl get endpoints <service-name> -n <namespace>
```
- 如果 Endpoints 为空 → Selector 没有匹配的 Pod，或 Pod 不是 Ready 状态
- 如果有 IP → 继续检查网络连通性

#### 从 Pod 内测试连通性
```
kubectl exec -it <pod-name> -n <namespace> -- curl -v <service-name>.<namespace>.svc.cluster.local:<port>
```

#### 常见 Service 问题
- **Endpoints 为空**：检查 Pod labels vs Service selector
- **连接超时**：CNI 插件问题、iptables/IPVS 规则异常
- **Connection refused**：目标 Pod 端口不对或应用未监听
- **跨 Node 通信失败**：CNI 网络插件问题、Node 防火墙

### Step 4: Ingress 问题

#### 检查 Ingress 配置
```
kubectl describe ingress <ingress-name> -n <namespace>
```
确认：
- `host` 是否匹配请求域名
- `path` 规则是否正确（注意 pathType: Prefix vs Exact）
- `backend` 指向的 Service 和 Port 是否正确

#### 检查 Ingress Controller
```
# Nginx Ingress Controller 日志
kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx --tail=100

# 检查 Ingress Controller Pod 状态
kubectl get pods -n ingress-nginx
```

#### 常见 Ingress 问题
- **404**：host 或 path 不匹配
- **502 Bad Gateway**：后端 Service 不可达或 Endpoints 为空
- **503 Service Unavailable**：后端 Pod 不健康（readinessProbe 失败）
- **504 Gateway Timeout**：后端处理超时，检查 `nginx.ingress.kubernetes.io/proxy-read-timeout`

### Step 5: 网络策略问题

#### 检查网络策略
```
kubectl get networkpolicy -n <namespace>
kubectl describe networkpolicy <policy-name> -n <namespace>
```

#### 常见 NetworkPolicy 问题
- **默认拒绝**：某些命名空间配置了 default-deny-all
- **egress/ingress 规则不匹配**：仔细检查 podSelector、namespaceSelector、port
- **缺少 DNS 放行**：网络策略阻止了到 CoreDNS 的 UDP 53 端口

## 修复建议
1. DNS 问题 → 优先检查 CoreDNS 状态和 Pod dnsPolicy
2. Service 问题 → 检查 Endpoints + Selector 匹配
3. Ingress 问题 → 从 Controller 日志入手
4. NetworkPolicy → 临时删除策略验证是否是策略导致
