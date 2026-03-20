// src/components/StatusBadge.tsx
/**
 * 状态徽章组件
 */
import { Tag } from 'antd';
import type { WorkflowStatus, HealthStatus } from '@/types/workflow';

interface StatusBadgeProps {
  status: WorkflowStatus | HealthStatus;
  type?: 'workflow' | 'health';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, type = 'workflow' }) => {
  if (type === 'workflow') {
    const colorMap: Record<WorkflowStatus, string> = {
      pending: 'default',
      running: 'processing',
      paused_approval: 'warning',
      completed: 'success',
      failed: 'error',
    };

    const textMap: Record<WorkflowStatus, string> = {
      pending: '待处理',
      running: '执行中',
      paused_approval: '等待审批',
      completed: '已完成',
      failed: '失败',
    };

    return (
      <Tag color={colorMap[status as WorkflowStatus]}>
        {textMap[status as WorkflowStatus] || status}
      </Tag>
    );
  }

  if (type === 'health') {
    const colorMap: Record<HealthStatus, string> = {
      healthy: 'success',
      degraded: 'warning',
      unhealthy: 'error',
    };

    const textMap: Record<HealthStatus, string> = {
      healthy: '健康',
      degraded: '降级',
      unhealthy: '不健康',
    };

    return (
      <Tag color={colorMap[status as HealthStatus]}>
        {textMap[status as HealthStatus] || status}
      </Tag>
    );
  }

  return <Tag>{status}</Tag>;
};
