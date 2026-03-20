// src/components/PrivateRoute.tsx
import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Spin, Result, Button } from 'antd';
import { useAuth } from '../contexts/AuthContext';
import { usePermission } from '../contexts/PermissionContext';

interface PrivateRouteProps {
  children: React.ReactNode;
  requiredPermission?: string;
}

export const PrivateRoute: React.FC<PrivateRouteProps> = ({ children, requiredPermission }) => {
  const { isAuthenticated, loading } = useAuth();
  const { hasPermission, loading: permissionLoading } = usePermission();
  const location = useLocation();

  if (loading || permissionLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // 如果需要权限检查但用户没有权限
  if (requiredPermission && !hasPermission(requiredPermission)) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <Result
          status="403"
          title="403"
          subTitle="抱歉，您没有权限访问此页面。"
          extra={
            <Button type="primary" onClick={() => window.history.back()}>
              返回
            </Button>
          }
        />
      </div>
    );
  }

  return <>{children}</>;
};
