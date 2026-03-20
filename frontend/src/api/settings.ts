// src/api/settings.ts
import { apiClient } from './client';

export interface SystemSetting {
  id: number;
  key: string;
  value: string;
  category: string;
  name: string;
  description: string | null;
  value_type: string;
  is_sensitive: boolean;
  is_readonly: boolean;
  created_at: string;
  updated_at: string;
}

export interface SystemSettingCreate {
  key: string;
  value: string;
  category: string;
  name: string;
  description?: string;
  value_type?: string;
  is_sensitive?: boolean;
  is_readonly?: boolean;
}

export interface SystemSettingUpdate {
  value?: string;
  name?: string;
  description?: string;
}

export interface SystemSettingBatchUpdate {
  settings: Record<string, any>;
}

export interface GroupedSettings {
  [category: string]: SystemSetting[];
}

export const settingsApi = {
  // 获取所有系统设置（按分类分组）
  getAll: async (): Promise<GroupedSettings> => {
    const response = await apiClient.get('/v1/settings');
    return response.data;
  },

  // 获取单个系统设置
  getByKey: async (key: string): Promise<SystemSetting> => {
    const response = await apiClient.get(`/v1/settings/${key}`);
    return response.data;
  },

  // 创建系统设置
  create: async (data: SystemSettingCreate): Promise<SystemSetting> => {
    const response = await apiClient.post('/v1/settings', data);
    return response.data;
  },

  // 更新系统设置
  update: async (key: string, data: SystemSettingUpdate): Promise<SystemSetting> => {
    const response = await apiClient.put(`/v1/settings/${key}`, data);
    return response.data;
  },

  // 批量更新系统设置
  batchUpdate: async (data: SystemSettingBatchUpdate): Promise<{ message: string; errors?: string }> => {
    const response = await apiClient.post('/v1/settings/batch', data);
    return response.data;
  },

  // 删除系统设置
  delete: async (key: string): Promise<void> => {
    await apiClient.delete(`/v1/settings/${key}`);
  },
};
