// src/api/chat.ts
/**
 * 聊天 API
 */
import { apiClient } from './client';
import { getToken } from '@/utils/auth';

// 使用与 client.ts 相同的配置
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

export interface ApprovalCommand {
  type: string;
  action: string;
  params?: any;
  reason?: string;
}

export interface PendingApprovalData {
  message?: string;
  commands?: ApprovalCommand[];
  [key: string]: any;
}

export interface ChatSession {
  session_id: string;
  title: string | null;
  source: 'web' | 'feishu';  // 会话来源
  username?: string | null;  // Web 用户名
  external_user_name?: string | null;  // 飞书用户名
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message?: string;
  // 会话状态
  state: 'normal' | 'awaiting_approval' | 'processing';
  pending_approval_data?: PendingApprovalData | null;
}

export interface ChatMessage {
  id: number;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  metadata?: any;
}

export interface ChatSessionListResponse {
  sessions: ChatSession[];
  total: number;
}

export const chatApi = {
  /**
   * 创建新会话
   */
  createSession: async (title?: string): Promise<ChatSession> => {
    const response = await apiClient.post('/v1/chat/sessions', { title });
    return response.data;
  },

  /**
   * 获取会话列表
   */
  getSessions: async (skip: number = 0, limit: number = 20): Promise<ChatSessionListResponse> => {
    const response = await apiClient.get('/v1/chat/sessions', {
      params: { skip, limit }
    });
    return response.data;
  },

  /**
   * 获取会话详情
   */
  getSession: async (sessionId: string): Promise<ChatSession> => {
    const response = await apiClient.get(`/v1/chat/sessions/${sessionId}`);
    return response.data;
  },

  /**
   * 删除会话
   */
  deleteSession: async (sessionId: string): Promise<void> => {
    await apiClient.delete(`/v1/chat/sessions/${sessionId}`);
  },

  /**
   * 获取消息历史
   */
  getMessages: async (sessionId: string, skip: number = 0, limit: number = 50): Promise<ChatMessage[]> => {
    const response = await apiClient.get(`/v1/chat/sessions/${sessionId}/messages`, {
      params: { skip, limit }
    });
    return response.data;
  },

  /**
   * 发送消息（普通 HTTP 请求/响应）
   */
  sendMessage: async (
    sessionId: string,
    content: string,
  ): Promise<{ reply: string; message_id?: number; workflow_status: string; needs_approval?: boolean; approval_data?: any }> => {
    const token = getToken();
    const response = await fetch(
      `${API_BASE_URL}/v1/chat/sessions/${sessionId}/messages`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ content }),
      }
    );
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: '请求失败' }));
      throw new Error(err.detail || err.reply || `HTTP ${response.status}`);
    }
    return response.json();
  },

  /**
   * 发送消息（流式响应，备用）
   * 使用 fetch API 实现 SSE 流式接收
   */
  sendMessageStream: async (
    sessionId: string,
    content: string,
    onChunk: (chunk: string) => void,
    onStatus: (status: string, message: string) => void,
    onApprovalRequest: (message: string, commands: any[], sessionId: string) => void,
    onDone: (messageId?: number) => void,
    onError: (error: Error) => void
  ): Promise<AbortController> => {
    const token = getToken();
    const abortController = new AbortController();

    try {
      const response = await fetch(
        `${API_BASE_URL}/v1/chat/sessions/${sessionId}/messages`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({ content }),
          signal: abortController.signal
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('Response body is null');
      }

      // 读取流式响应
      const readStream = async () => {
        try {
          while (true) {
            const { done, value } = await reader.read();

            if (done) {
              break;
            }

            // 解码数据
            const chunk = decoder.decode(value, { stream: true });

            // 处理 SSE 数据（可能包含多个事件）
            const lines = chunk.split('\n');

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const data = line.substring(6); // 移除 "data: " 前缀

                try {
                  const parsed = JSON.parse(data);

                  if (parsed.type === 'chunk') {
                    onChunk(parsed.content);
                  } else if (parsed.type === 'status') {
                    onStatus(parsed.status, parsed.message);
                  } else if (parsed.type === 'approval_request') {
                    // 新增：处理批准请求
                    onApprovalRequest(parsed.message, parsed.commands, parsed.session_id);
                  } else if (parsed.type === 'done') {
                    onDone(parsed.message_id);
                  } else if (parsed.type === 'error') {
                    onError(new Error(parsed.message));
                  }
                } catch (e) {
                  // 忽略 JSON 解析错误（可能是不完整的数据）
                  console.warn('Failed to parse SSE data:', data);
                }
              }
            }
          }
        } catch (error) {
          if (error instanceof Error && error.name !== 'AbortError') {
            onError(error);
          }
        }
      };

      // 异步读取流
      readStream();

    } catch (error) {
      if (error instanceof Error && error.name !== 'AbortError') {
        onError(error);
      }
    }

    return abortController;
  },

  /**
   * 恢复暂停的工作流（发送批准决定）
   * 注意：流式请求使用 fetch 而不是 axios
   */
  resumeWorkflow: async (
    sessionId: string,
    approvalStatus: 'approved' | 'rejected',
    onChunk: (chunk: string) => void,
    onStatus: (status: string, message: string) => void,
    onApprovalRequest: (message: string, commands: any[], sessionId: string) => void,
    onDone: () => void,
    onError: (error: Error) => void
  ): Promise<AbortController> => {
    const token = getToken();
    const abortController = new AbortController();

    try {
      const response = await fetch(
        `${API_BASE_URL}/v1/chat/sessions/${sessionId}/resume`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({ status: approvalStatus }),
          signal: abortController.signal
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('Response body is null');
      }

      // 读取流式响应
      const readStream = async () => {
        try {
          while (true) {
            const { done, value } = await reader.read();

            if (done) {
              break;
            }

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const data = line.substring(6);

                try {
                  const parsed = JSON.parse(data);

                  if (parsed.type === 'chunk') {
                    onChunk(parsed.content);
                  } else if (parsed.type === 'status') {
                    onStatus(parsed.status, parsed.message);
                  } else if (parsed.type === 'approval_request') {
                    // 可能有多个批准点
                    onApprovalRequest(parsed.message, parsed.commands, parsed.session_id);
                  } else if (parsed.type === 'done') {
                    onDone();
                  } else if (parsed.type === 'error') {
                    onError(new Error(parsed.message));
                  }
                } catch (e) {
                  console.warn('Failed to parse SSE data:', data);
                }
              }
            }
          }
        } catch (error) {
          if (error instanceof Error && error.name !== 'AbortError') {
            onError(error);
          }
        }
      };

      readStream();

    } catch (error) {
      if (error instanceof Error && error.name !== 'AbortError') {
        onError(error);
      }
    }

    return abortController;
  }
};
