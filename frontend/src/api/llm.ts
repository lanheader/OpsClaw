// src/api/llm.ts
/**
 * LLM 测试 API
 */
import { apiClient } from './client';

export interface LLMTestRequest {
  provider: 'openai' | 'claude' | 'zhipu' | 'ollama';
}

export interface LLMTestResponse {
  success: boolean;
  provider: string;
  model: string;
  response_time_ms?: number;
  test_message?: string;
  error?: string;
}

export const llmAPI = {
  /**
   * 测试 LLM 连接
   */
  test: async (request: LLMTestRequest): Promise<LLMTestResponse> => {
    const response = await apiClient.post<LLMTestResponse>(
      '/v1/llm/test',
      request
    );
    return response.data;
  },
};
