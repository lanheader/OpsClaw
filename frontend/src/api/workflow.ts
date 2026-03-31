// src/api/workflow.ts
/**
 * 工作流 API
 */
import { apiClient } from './client';
import type {
  WorkflowExecuteRequest,
  WorkflowExecuteResponse,
  WorkflowStatusResponse,
  WorkflowResumeRequest,
} from '@/types/workflow';

export const workflowAPI = {
  /**
   * 执行新的工作流
   */
  execute: async (request: WorkflowExecuteRequest): Promise<WorkflowExecuteResponse> => {
    const response = await apiClient.post<WorkflowExecuteResponse>(
      '/v1/workflow/execute',
      request
    );
    return response.data;
  },

  /**
   * 获取工作流状态
   */
  getStatus: async (taskId: string): Promise<WorkflowStatusResponse> => {
    const response = await apiClient.get<WorkflowStatusResponse>(
      `/v1/workflow/${taskId}/status`
    );
    return response.data;
  },

  /**
   * 恢复暂停的工作流
   */
  resume: async (
    taskId: string,
    request: WorkflowResumeRequest
  ): Promise<WorkflowExecuteResponse> => {
    const response = await apiClient.post<WorkflowExecuteResponse>(
      `/v1/workflow/${taskId}/resume`,
      request
    );
    return response.data;
  },

  /**
   * 获取健康状态
   */
  getHealth: async (): Promise<any> => {
    const response = await apiClient.get('/v1/health');
    return response.data;
  },
};
