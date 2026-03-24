// src/api/client.ts
/**
 * Axios 客户端配置
 */
import axios from 'axios';
import { message } from 'antd';
import { getToken, removeToken } from '@/utils/auth';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器 - 自动添加 token
apiClient.interceptors.request.use(
  (config) => {
    const token = getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器 - 统一错误处理
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    let errorMessage = '请求失败';

    if (error.response) {
      // 服务器返回错误
      const status = error.response.status;
      const data = error.response.data;

      switch (status) {
        case 401:
          // Token 过期或未授权
          errorMessage = '登录已过期，请重新登录';
          removeToken();
          // 延迟跳转，让用户看到错误提示
          setTimeout(() => {
            window.location.href = '/login';
          }, 1500);
          break;
        case 403:
          errorMessage = '没有权限访问此资源';
          break;
        case 404:
          errorMessage = '请求的资源不存在';
          break;
        case 500:
          errorMessage = '服务器内部错误';
          break;
        default:
          // 处理 FastAPI 验证错误（detail 可能是数组）
          if (data?.detail) {
            if (typeof data.detail === 'string') {
              errorMessage = data.detail;
            } else if (Array.isArray(data.detail)) {
              // FastAPI 验证错误格式
              errorMessage = data.detail.map((err: any) => err.msg || err.message).join('; ');
            } else if (typeof data.detail === 'object') {
              errorMessage = data.detail.msg || data.detail.message || JSON.stringify(data.detail);
            }
          } else {
            errorMessage = data?.message || `请求失败 (${status})`;
          }
      }

      console.error('API Error:', {
        status,
        url: error.config?.url,
        data: error.response.data,
      });
    } else if (error.request) {
      // 网络错误
      errorMessage = '网络连接失败，请检查网络';
      console.error('Network Error:', error.message);
    } else {
      // 其他错误
      errorMessage = error.message || '请求失败';
      console.error('Error:', error.message);
    }

    // 使用 setTimeout 避免 React 18 concurrent 警告
    setTimeout(() => message.error(errorMessage), 0);
    return Promise.reject(error);
  }
);
