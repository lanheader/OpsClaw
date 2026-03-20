// src/contexts/PermissionContext.tsx
import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { apiClient } from '@/api/client';
import { useAuth } from './AuthContext';

interface PermissionContextType {
  permissions: string[];
  roles: string[];
  loading: boolean;
  hasPermission: (permission: string) => boolean;
  hasAnyPermission: (permissions: string[]) => boolean;
  hasAllPermissions: (permissions: string[]) => boolean;
  hasRole: (role: string) => boolean;
  refreshPermissions: () => Promise<void>;
}

const PermissionContext = createContext<PermissionContextType | undefined>(undefined);

interface PermissionProviderProps {
  children: ReactNode;
}

export const PermissionProvider: React.FC<PermissionProviderProps> = ({ children }) => {
  const [permissions, setPermissions] = useState<string[]>([]);
  const [roles, setRoles] = useState<string[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const { token } = useAuth(); // 获取 token 状态

  const fetchPermissions = async () => {
    try {
      if (!token) {
        setPermissions([]);
        setRoles([]);
        setLoading(false);
        return;
      }

      const response = await apiClient.get('/v1/permissions/me');

      setPermissions(response.data.permissions || []);
      setRoles(response.data.roles || []);
    } catch (error) {
      console.error('Failed to fetch permissions:', error);
      setPermissions([]);
      setRoles([]);
    } finally {
      setLoading(false);
    }
  };

  // 监听 token 变化，当 token 变化时重新获取权限
  useEffect(() => {
    setLoading(true);
    fetchPermissions();
  }, [token]); // 依赖 token，当 token 变化时重新获取

  const hasPermission = (permission: string): boolean => {
    return permissions.includes(permission);
  };

  const hasAnyPermission = (perms: string[]): boolean => {
    return perms.some(p => permissions.includes(p));
  };

  const hasAllPermissions = (perms: string[]): boolean => {
    return perms.every(p => permissions.includes(p));
  };

  const hasRole = (role: string): boolean => {
    return roles.includes(role);
  };

  const refreshPermissions = async (): Promise<void> => {
    setLoading(true);
    await fetchPermissions();
  };

  const value: PermissionContextType = {
    permissions,
    roles,
    loading,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    hasRole,
    refreshPermissions,
  };

  return (
    <PermissionContext.Provider value={value}>
      {children}
    </PermissionContext.Provider>
  );
};

export const usePermission = (): PermissionContextType => {
  const context = useContext(PermissionContext);
  if (context === undefined) {
    throw new Error('usePermission must be used within a PermissionProvider');
  }
  return context;
};
