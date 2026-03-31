// src/api/kubernetes.ts
/**
 * Kubernetes 配置管理 API
 */

import { apiClient } from './client';

// ========== 类型定义 ==========

export type AuthMode = 'kubeconfig' | 'token';

export interface KubernetesConfig {
  enabled: boolean;
  auth_mode: AuthMode;
  kubeconfig_content_masked?: string;
  api_host?: string;
  token_masked?: string;
  ca_cert_masked?: string;
}

export interface KubernetesConfigUpdate {
  enabled?: boolean;
  auth_mode: AuthMode;
  kubeconfig_content?: string;
  api_host?: string;
  token?: string;
  ca_cert?: string;
}

export interface KubernetesConnectionTestRequest {
  auth_mode?: AuthMode;
  kubeconfig_content?: string;
  api_host?: string;
  token?: string;
  ca_cert?: string;
}

export interface KubernetesConnectionTestResponse {
  success: boolean;
  message: string;
  cluster_info?: string;
  server_version?: string;
  response_time_ms?: number;
}

// ========== API 函数 ==========

export const kubernetesApi = {
  /**
   * 获取 Kubernetes 配置
   */
  getConfig: async (): Promise<KubernetesConfig> => {
    const response = await apiClient.get<KubernetesConfig>('/v1/integrations/kubernetes/config');
    return response.data;
  },

  /**
   * 更新 Kubernetes 配置
   */
  updateConfig: async (data: KubernetesConfigUpdate): Promise<KubernetesConfig> => {
    const response = await apiClient.put<KubernetesConfig>('/v1/integrations/kubernetes/config', data);
    return response.data;
  },

  /**
   * 测试 Kubernetes 连接
   */
  testConnection: async (
    request?: KubernetesConnectionTestRequest
  ): Promise<KubernetesConnectionTestResponse> => {
    const response = await apiClient.post<KubernetesConnectionTestResponse>(
      '/v1/integrations/kubernetes/test',
      request || {}
    );
    return response.data;
  },
};
