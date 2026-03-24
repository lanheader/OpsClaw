// src/api/approvalConfig.ts
/**
 * 审批配置管理 API
 */

import { apiClient } from './client';

// ========== 类型定义 ==========

export interface ToolApprovalConfig {
  id: number;
  tool_name: string;
  tool_group: string | null;
  risk_level: string | null;
  requires_approval: boolean;
  approval_roles: string[] | null;
  exempt_roles: string[] | null;
  description: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface SyncToolsResponse {
  synced_count: number;
  total_count: number;
}

export interface BatchUpdateRequest {
  tool_names: string[];
  requires_approval: boolean;
}

export interface BatchUpdateResponse {
  updated_count: number;
}

export interface UpdateToolApprovalResponse {
  success: boolean;
  tool_name: string;
  requires_approval: boolean;
}

// ========== API 函数 ==========

/**
 * 同步工具到配置表
 */
export const syncTools = async (): Promise<SyncToolsResponse> => {
  const response = await apiClient.post<SyncToolsResponse>('/v1/approval-config/sync');
  return response.data;
};

/**
 * 获取审批配置列表
 */
export const getApprovalTools = async (params?: {
  group?: string;
  risk_level?: string;
}): Promise<ToolApprovalConfig[]> => {
  const response = await apiClient.get<ToolApprovalConfig[]>('/v1/approval-config/tools', {
    params
  });
  return response.data;
};

/**
 * 获取所有工具分组
 */
export const getApprovalGroups = async (): Promise<string[]> => {
  const response = await apiClient.get<string[]>('/v1/approval-config/tools/groups');
  return response.data;
};

/**
 * 获取单个工具的审批配置
 */
export const getToolConfig = async (toolName: string): Promise<ToolApprovalConfig> => {
  const response = await apiClient.get<ToolApprovalConfig>(
    `/v1/approval-config/tools/${toolName}`
  );
  return response.data;
};

/**
 * 更新工具审批状态
 */
export const updateToolApproval = async (
  toolName: string,
  requiresApproval: boolean
): Promise<UpdateToolApprovalResponse> => {
  const response = await apiClient.put<UpdateToolApprovalResponse>(
    `/v1/approval-config/tools/${toolName}`,
    null,
    {
      params: { requires_approval: requiresApproval }
    }
  );
  return response.data;
};

/**
 * 批量更新工具审批状态
 */
export const batchUpdateApproval = async (
  request: BatchUpdateRequest
): Promise<BatchUpdateResponse> => {
  const response = await apiClient.put<BatchUpdateResponse>(
    '/v1/approval-config/tools/batch',
    request
  );
  return response.data;
};

/**
 * 获取需要审批的工具列表
 */
export const getToolsRequireApproval = async (userRole?: string): Promise<string[]> => {
  const response = await apiClient.get<string[]>('/v1/approval-config/require-approval', {
    params: userRole ? { user_role: userRole } : undefined
  });
  return response.data;
};

// 导出为 approvalConfigApi 对象
export const approvalConfigApi = {
  syncTools,
  getApprovalTools,
  getApprovalGroups,
  getToolConfig,
  updateToolApproval,
  batchUpdateApproval,
  getToolsRequireApproval
};
