// src/api/feishu.ts
/**
 * 飞书集成 API
 */
import { apiClient } from './client';
import type { FeishuStatus } from '@/types/feishu';

export const feishuAPI = {
  /**
   * 获取飞书集成状态
   */
  getStatus: async (): Promise<FeishuStatus> => {
    const response = await apiClient.get<FeishuStatus>('/v1/feishu/status');
    return response.data;
  },

  /**
   * 发送测试消息
   */
  sendTestMessage: async (text: string): Promise<any> => {
    const response = await apiClient.post(`/v1/feishu/test-message?text=${encodeURIComponent(text)}`);
    return response.data;
  },
};
