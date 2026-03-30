// src/api/prompts.ts
/**
 * 提示词管理 API
 */

import { apiClient } from './client';

// ========== 类型定义 ==========

export interface AgentPrompt {
  id: number;
  agent_name: string;
  name: string;
  description: string | null;
  content: string;
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AgentPromptListItem {
  id: number;
  agent_name: string;
  name: string;
  description: string | null;
  version: number;
  is_active: boolean;
  content_preview: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentPromptCreate {
  agent_name: string;
  name: string;
  description?: string;
  content: string;
}

export interface AgentPromptUpdate {
  name?: string;
  description?: string;
  content?: string;
  is_active?: boolean;
}

export interface PromptVersion {
  id: number;
  prompt_id: number;
  agent_name: string;
  version: number;
  content: string;
  change_summary: string | null;
  changed_by: string | null;
  created_at: string;
}

export interface PromptVersionListItem {
  id: number;
  prompt_id: number;
  agent_name: string;
  version: number;
  content_preview: string | null;
  change_summary: string | null;
  changed_by: string | null;
  created_at: string;
}

export interface RollbackResponse {
  success: boolean;
  message: string;
  current_version: number;
}

export interface ClearCacheResponse {
  message: string;
}

// ========== API 函数 ==========

export const promptsApi = {
  // 获取所有提示词（列表视图）
  getAll: async (): Promise<AgentPromptListItem[]> => {
    const response = await apiClient.get<AgentPromptListItem[]>('/v1/prompts');
    return response.data;
  },

  // 获取单个提示词（完整内容）
  getByName: async (agentName: string): Promise<AgentPrompt> => {
    const response = await apiClient.get<AgentPrompt>(`/v1/prompts/${agentName}`);
    return response.data;
  },

  // 创建提示词
  create: async (data: AgentPromptCreate): Promise<AgentPrompt> => {
    const response = await apiClient.post<AgentPrompt>('/v1/prompts', data);
    return response.data;
  },

  // 更新提示词
  update: async (agentName: string, data: AgentPromptUpdate): Promise<AgentPrompt> => {
    const response = await apiClient.put<AgentPrompt>(`/v1/prompts/${agentName}`, data);
    return response.data;
  },

  // 获取版本历史（列表视图）
  getVersions: async (agentName: string): Promise<PromptVersionListItem[]> => {
    const response = await apiClient.get<PromptVersionListItem[]>(`/v1/prompts/${agentName}/versions`);
    return response.data;
  },

  // 获取指定版本的完整内容
  getVersionContent: async (agentName: string, version: number): Promise<PromptVersion> => {
    const response = await apiClient.get<PromptVersion>(`/v1/prompts/${agentName}/versions/${version}`);
    return response.data;
  },

  // 回滚到指定版本
  rollback: async (agentName: string, targetVersion: number): Promise<RollbackResponse> => {
    const response = await apiClient.post<RollbackResponse>(
      `/v1/prompts/${agentName}/rollback`,
      { target_version: targetVersion }
    );
    return response.data;
  },

  // 清除缓存
  clearCache: async (): Promise<ClearCacheResponse> => {
    const response = await apiClient.post<ClearCacheResponse>('/v1/prompts/clear-cache');
    return response.data;
  }
};
