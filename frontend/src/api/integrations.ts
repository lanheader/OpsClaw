// src/api/integrations.ts
/**
 * 外部系统集成测试 API
 */
import { apiClient } from './client';

export interface IntegrationTestResponse {
  success: boolean;
  service: string;
  response_time_ms?: number;
  version?: string;
  details?: Record<string, any>;
  error?: string;
}

export const integrationsAPI = {
  /**
   * 测试 Kubernetes 连接
   */
  testKubernetes: async (): Promise<IntegrationTestResponse> => {
    const response = await apiClient.post<IntegrationTestResponse>(
      '/v1/integrations/test/kubernetes'
    );
    return response.data;
  },

  /**
   * 测试 Prometheus 连接
   */
  testPrometheus: async (): Promise<IntegrationTestResponse> => {
    const response = await apiClient.post<IntegrationTestResponse>(
      '/v1/integrations/test/prometheus'
    );
    return response.data;
  },

  /**
   * 测试 Loki 连接
   */
  testLoki: async (): Promise<IntegrationTestResponse> => {
    const response = await apiClient.post<IntegrationTestResponse>(
      '/v1/integrations/test/loki'
    );
    return response.data;
  },

  /**
   * 测试飞书连接
   */
  testFeishu: async (): Promise<IntegrationTestResponse> => {
    const response = await apiClient.post<IntegrationTestResponse>(
      '/v1/integrations/test/feishu'
    );
    return response.data;
  },
};
