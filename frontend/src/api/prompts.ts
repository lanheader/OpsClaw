/**
 * 提示词管理 API
 */

import { apiClient } from './client';

export interface PromptListItem {
  id: number;
  subagent_name: string;
  version: string;
  prompt_type: string;
  is_active: boolean;
  is_latest: boolean;
  content_preview: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface PromptDetail extends PromptListItem {
  prompt_content: string;
  few_shot_examples: any[] | null;
  performance_score: number;
  usage_count: number;
  optimization_metadata: any | null;
}

export interface PromptStats {
  total_prompts: number;
  by_subagent: Record<string, number>;
  by_type: Record<string, number>;
  latest_versions: Array<{
    subagent_name: string;
    version: string;
    type: string;
    is_active: boolean;
  }>;
}

export interface ChangeLog {
  id: number;
  subagent_name: string;
  change_type: string;
  old_version: string | null;
  new_version: string;
  change_reason: string | null;
  changed_at: string;
  optimization_method: string | null;
  training_examples_count: number | null;
  old_content: string | null;
  new_content: string | null;
}

export interface UpdatePromptRequest {
  content: string;
  notes?: string;
}

export interface CurrentPromptInfo {
  subagent_name: string;
  prompt_content: string;
  version: string;
  type: string;
  is_optimized: boolean;
  prompt_length: number;
}

/**
 * 提示词管理 API
 */
export const promptsApi = {
  /**
   * 获取提示词统计信息
   */
  getStats: async (): Promise<PromptStats> => {
    const response = await apiClient.get<PromptStats>('/v2/prompts/stats');
    return response.data;
  },

  /**
   * 获取提示词列表
   */
  listPrompts: async (params?: {
    subagent_name?: string;
    prompt_type?: string;
  }): Promise<PromptListItem[]> => {
    const response = await apiClient.get<PromptListItem[]>('/v2/prompts/list', {
      params,
    });
    return response.data;
  },

  /**
   * 获取提示词详情
   */
  getPromptDetail: async (id: number): Promise<PromptDetail> => {
    const response = await apiClient.get<PromptDetail>(`/v2/prompts/${id}`);
    return response.data;
  },

  /**
   * 更新提示词
   */
  updatePrompt: async (id: number, data: UpdatePromptRequest): Promise<{
    message: string;
    prompt_id: number;
    version: string;
    note: string;
  }> => {
    const response = await apiClient.put(`/v2/prompts/${id}`, data);
    return response.data;
  },

  /**
   * 激活指定版本的提示词
   */
  activatePrompt: async (id: number): Promise<{
    message: string;
    prompt_id: number;
    version: string;
  }> => {
    const response = await apiClient.post(`/v2/prompts/${id}/activate`);
    return response.data;
  },

  /**
   * 初始化基础提示词
   */
  initializePrompts: async (): Promise<{
    message: string;
    initialized: string[];
  }> => {
    const response = await apiClient.post('/v2/prompts/initialize');
    return response.data;
  },

  /**
   * 手动触发 DSPy 优化
   */
  triggerOptimization: async (subagentName: string): Promise<{
    message: string;
    subagent_name: string;
    prompt_length: number;
  }> => {
    const response = await apiClient.post(`/v2/prompts/optimize/${subagentName}`);
    return response.data;
  },

  /**
   * 获取变更日志
   */
  getChangeLogs: async (params?: {
    subagent_name?: string;
    limit?: number;
  }): Promise<{
    total: number;
    logs: ChangeLog[];
  }> => {
    const response = await apiClient.get<{ total: number; logs: ChangeLog[] }>('/v2/prompts/logs', {
      params,
    });
    return response.data;
  },

  /**
   * 获取当前使用的提示词
   */
  getCurrentPrompt: async (subagentName: string): Promise<CurrentPromptInfo> => {
    const response = await apiClient.get<CurrentPromptInfo>(`/v2/prompts/current/${subagentName}`);
    return response.data;
  },
};
