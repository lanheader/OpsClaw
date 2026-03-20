// src/api/users.ts
import { apiClient } from './client';
import type { User } from './auth';

export interface UserCreateRequest {
  username: string;
  email: string;
  password: string;
  full_name?: string;
  is_active?: boolean;
  is_superuser?: boolean;
}

export interface UserUpdateRequest {
  email?: string;
  full_name?: string;
  feishu_user_id?: string;
  is_active?: boolean;
  is_superuser?: boolean;
}

export interface ResetPasswordRequest {
  new_password: string;
}

export interface UserRole {
  id: number;
  name: string;
  code: string;
  description: string | null;
}

export interface AssignRolesRequest {
  role_ids: number[];
}

export const usersApi = {
  getUsers: async (): Promise<User[]> => {
    const response = await apiClient.get('/v1/users');
    return response.data;
  },

  getUser: async (id: number): Promise<User> => {
    const response = await apiClient.get(`/v1/users/${id}`);
    return response.data;
  },

  createUser: async (data: UserCreateRequest): Promise<User> => {
    const response = await apiClient.post('/v1/users', data);
    return response.data;
  },

  updateUser: async (id: number, data: UserUpdateRequest): Promise<User> => {
    const response = await apiClient.put(`/v1/users/${id}`, data);
    return response.data;
  },

  deleteUser: async (id: number): Promise<void> => {
    await apiClient.delete(`/v1/users/${id}`);
  },

  resetPassword: async (id: number, data: ResetPasswordRequest): Promise<void> => {
    await apiClient.post(`/v1/users/${id}/reset-password`, data);
  },

  // User-Role Management APIs
  getUserRoles: async (id: number): Promise<UserRole[]> => {
    const response = await apiClient.get(`/v1/users/${id}/roles`);
    return response.data;
  },

  assignRoles: async (id: number, data: AssignRolesRequest): Promise<void> => {
    await apiClient.put(`/v1/users/${id}/roles`, data);
  }
};
