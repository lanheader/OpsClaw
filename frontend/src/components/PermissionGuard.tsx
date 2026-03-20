// src/components/PermissionGuard.tsx
import React, { ReactNode } from 'react';
import { usePermission } from '../contexts/PermissionContext';

interface PermissionGuardProps {
  permission?: string;
  permissions?: string[];
  requireAll?: boolean;
  role?: string;
  children: ReactNode;
  fallback?: ReactNode;
}

export const PermissionGuard: React.FC<PermissionGuardProps> = ({
  permission,
  permissions,
  requireAll = false,
  role,
  children,
  fallback = null,
}) => {
  const { hasPermission, hasAnyPermission, hasAllPermissions, hasRole, loading } = usePermission();

  // 如果正在加载权限，显示 fallback
  if (loading) {
    return <>{fallback}</>;
  }

  // 检查角色
  if (role && !hasRole(role)) {
    return <>{fallback}</>;
  }

  // 检查单个权限
  if (permission && !hasPermission(permission)) {
    return <>{fallback}</>;
  }

  // 检查多个权限
  if (permissions && permissions.length > 0) {
    const hasAccess = requireAll
      ? hasAllPermissions(permissions)
      : hasAnyPermission(permissions);

    if (!hasAccess) {
      return <>{fallback}</>;
    }
  }

  return <>{children}</>;
};
