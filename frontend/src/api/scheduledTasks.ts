import { apiClient } from './client';

export interface ScheduledTask {
  id: number;
  name: string;
  description: string | null;
  task_type: string;
  cron_expr: string;
  timezone: string;
  task_params: string | null;
  enabled: boolean;
  timeout: number;
  notify_on_fail: boolean;
  notify_target: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskExecution {
  id: number;
  task_id: number;
  task_name?: string;
  status: string;
  trigger_type: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  result_summary: string | null;
  error_message: string | null;
}

export interface TaskStats {
  total: number;
  enabled: number;
  today_stats: {
    total: number;
    running: number;
    success: number;
    failed: number;
  };
}

export interface TaskCreate {
  name: string;
  description?: string;
  task_type: string;
  cron_expr: string;
  timezone?: string;
  task_params?: string;
  enabled?: boolean;
  timeout?: number;
  notify_on_fail?: boolean;
  notify_target?: string;
}

export interface TaskUpdate {
  name?: string;
  description?: string;
  task_type?: string;
  cron_expr?: string;
  timezone?: string;
  task_params?: string;
  enabled?: boolean;
  timeout?: number;
  notify_on_fail?: boolean;
  notify_target?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export const scheduledTasksApi = {
  getTasks: async (page = 1, pageSize = 20): Promise<PaginatedResponse<ScheduledTask>> => {
    const res = await apiClient.get('/v1/tasks', { params: { page, page_size: pageSize } });
    return res.data;
  },

  getStats: async (): Promise<TaskStats> => {
    const res = await apiClient.get('/v1/tasks/stats');
    return res.data;
  },

  getTask: async (id: number): Promise<ScheduledTask> => {
    const res = await apiClient.get(`/v1/tasks/${id}`);
    return res.data;
  },

  createTask: async (data: TaskCreate): Promise<ScheduledTask> => {
    const res = await apiClient.post('/v1/tasks', data);
    return res.data;
  },

  updateTask: async (id: number, data: TaskUpdate): Promise<ScheduledTask> => {
    const res = await apiClient.put(`/v1/tasks/${id}`, data);
    return res.data;
  },

  deleteTask: async (id: number): Promise<void> => {
    await apiClient.delete(`/v1/tasks/${id}`);
  },

  toggleTask: async (id: number): Promise<{ message: string; enabled: boolean }> => {
    const res = await apiClient.post(`/v1/tasks/${id}/toggle`);
    return res.data;
  },

  runTask: async (id: number): Promise<{ message: string }> => {
    const res = await apiClient.post(`/v1/tasks/${id}/run`);
    return res.data;
  },

  getTaskExecutions: async (taskId: number, page = 1, pageSize = 20): Promise<PaginatedResponse<TaskExecution>> => {
    const res = await apiClient.get(`/v1/tasks/${taskId}/executions`, { params: { page, page_size: pageSize } });
    return res.data;
  },

  getAllExecutions: async (page = 1, pageSize = 20, taskId?: number): Promise<PaginatedResponse<TaskExecution>> => {
    const res = await apiClient.get('/v1/tasks/executions', { params: { page, page_size: pageSize, task_id: taskId } });
    return res.data;
  },
};
