// src/api/onboarding.ts
import { apiClient } from './client';

export interface OnboardingStatus {
  initialized: boolean;
  step: number;
}

export interface Step1Data {
  password: string;
  email: string;
  feishu_user_id: string;
}

export interface K8sConfig {
  enabled: boolean;
  api_host?: string;
  auth_mode?: 'kubeconfig' | 'token';
  kubeconfig?: string;
  token?: string;
}

export interface PrometheusConfig {
  enabled: boolean;
  url?: string;
}

export interface LokiConfig {
  enabled: boolean;
  url?: string;
}

export interface OnboardingSummary {
  account_configured: boolean;
  k8s_enabled: boolean;
  prometheus_enabled: boolean;
  loki_enabled: boolean;
}

export const onboardingApi = {
  // 获取初始化状态
  getStatus: async (): Promise<OnboardingStatus> => {
    const response = await apiClient.get('/v1/onboarding/status');
    return response.data;
  },

  // Step 1: 账户设置
  submitStep1: async (data: Step1Data): Promise<{ message: string; step: number }> => {
    const response = await apiClient.post('/v1/onboarding/step1', data);
    return response.data;
  },

  // Step 2: Kubernetes 配置
  submitStep2: async (data: K8sConfig): Promise<{ message: string; step: number }> => {
    const response = await apiClient.post('/v1/onboarding/step2', data);
    return response.data;
  },

  // Step 3: Prometheus 配置
  submitStep3: async (data: PrometheusConfig): Promise<{ message: string; step: number }> => {
    const response = await apiClient.post('/v1/onboarding/step3', data);
    return response.data;
  },

  // Step 4: Loki 配置
  submitStep4: async (data: LokiConfig): Promise<{ message: string; step: number }> => {
    const response = await apiClient.post('/v1/onboarding/step4', data);
    return response.data;
  },

  // 完成初始化
  complete: async (): Promise<OnboardingSummary> => {
    const response = await apiClient.post('/v1/onboarding/complete');
    return response.data;
  },
};
