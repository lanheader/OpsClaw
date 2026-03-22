// src/api/auth.ts
import { apiClient } from './client';
import { getToken } from '@/utils/auth';

export interface LoginRequest {
  username: string;
  password: string;
  remember: boolean;
}

export interface User {
  id: number;
  username: string;
  email: string;
  full_name: string | null;
  feishu_user_id: string | null;
  avatar_url?: string | null;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export const authApi = {
  login: async (data: LoginRequest): Promise<LoginResponse> => {
    const response = await apiClient.post('/v1/auth/login', data);
    return response.data;
  },

  logout: async (): Promise<void> => {
    const token = getToken();
    if (token) {
      await apiClient.post('/v1/auth/logout');
    }
  },

  getCurrentUser: async (): Promise<User> => {
    const response = await apiClient.get('/v1/auth/me');
    return response.data;
  }
};
