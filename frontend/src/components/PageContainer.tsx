// src/components/PageContainer.tsx
/**
 * 统一页面容器组件
 * 用于所有管理页面的布局包装
 */
import React from 'react';
import { Typography } from 'antd';
import type { ReactNode } from 'react';

const { Title, Text } = Typography;

interface PageContainerProps {
  title: string;
  description?: string;
  children: ReactNode;
  extra?: ReactNode;
  icon?: ReactNode;
}

export const PageContainer: React.FC<PageContainerProps> = ({
  title,
  description,
  children,
  extra,
  icon
}) => {
  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
        <div>
          <Title level={2} style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
            {icon && <span style={{ fontSize: 28 }}>{icon}</span>}
            {title}
          </Title>
          {description && <Text type="secondary">{description}</Text>}
        </div>
        {extra && <div style={{ marginTop: 4 }}>{extra}</div>}
      </div>
      {children}
    </div>
  );
};
