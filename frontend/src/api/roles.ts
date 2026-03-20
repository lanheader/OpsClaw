// src/api/roles.ts
import { apiClient } from './client';

export interface Role {
  id: number;
  name: string;
  code: string;
  description: string | null;
  is_system: boolean;
  created_at: string;
  updated_at: string;
}

export interface Permission {
  code: string;
  name: string;
  category: 'menu' | 'tool' | 'api';
  resource: string;
  description: string;
}

export interface RoleWithPermissions extends Role {
  permissions: Permission[];
}

export interface RoleCreateRequest {
  name: string;
  code: string;
  description?: string;
}

export interface RoleUpdateRequest {
  name?: string;
  description?: string;
}

export interface UpdatePermissionsRequest {
  permission_codes: string[];
}

export const rolesApi = {
  getRoles: async (): Promise<Role[]> => {
    const response = await apiClient.get('/v1/roles');
    return response.data;
  },

  getRole: async (id: number): Promise<RoleWithPermissions> => {
    const response = await apiClient.get(`/v1/roles/${id}`);
    return response.data;
  },

  createRole: async (data: RoleCreateRequest): Promise<Role> => {
    const response = await apiClient.post('/v1/roles', data);
    return response.data;
  },

  updateRole: async (id: number, data: RoleUpdateRequest): Promise<Role> => {
    const response = await apiClient.put(`/v1/roles/${id}`, data);
    return response.data;
  },

  deleteRole: async (id: number): Promise<void> => {
    await apiClient.delete(`/v1/roles/${id}`);
  },

  getRolePermissions: async (id: number): Promise<Permission[]> => {
    const response = await apiClient.get(`/v1/roles/${id}/permissions`);
    return response.data;
  },

  updateRolePermissions: async (id: number, data: UpdatePermissionsRequest): Promise<void> => {
    await apiClient.put(`/v1/roles/${id}/permissions`, data);
  },

  getAllPermissions: async (): Promise<Record<string, Permission[]>> => {
    const response = await apiClient.get('/v1/permissions');
    return response.data;
  }
};
