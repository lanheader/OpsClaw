import { apiClient } from './client';

export const scheduledTasksApi = {
  getStats: async () => {
    try {
      const res = await apiClient.get('/scheduled-tasks/stats');
      return res.data;
    } catch {
      // 后端接口尚未实现，返回默认值
      return { total: 0, running: 0, completed: 0, failed: 0 };
    }
  },
};
