// src/components/WorkflowCard.tsx
/**
 * 工作流卡片组件
 */
import { Card, Space, Typography } from 'antd';
import { ClockCircleOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { StatusBadge } from './StatusBadge';
import type { WorkflowListItem } from '@/types/workflow';
import dayjs from 'dayjs';

const { Text } = Typography;

interface WorkflowCardProps {
  workflow: WorkflowListItem;
  onClick?: () => void;
}

export const WorkflowCard: React.FC<WorkflowCardProps> = ({ workflow, onClick }) => {
  const getIcon = () => {
    if (workflow.status === 'completed' && workflow.success) {
      return <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 24 }} />;
    }
    if (workflow.status === 'failed' || (workflow.status === 'completed' && !workflow.success)) {
      return <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 24 }} />;
    }
    return <ClockCircleOutlined style={{ color: '#1890ff', fontSize: 24 }} />;
  };

  const taskTypeMap: Record<string, string> = {
    scheduled_inspection: '定期巡检',
    alert_triggered: '告警触发',
    manual_command: '手动命令',
    emergency_response: '紧急响应',
  };

  return (
    <Card
      hoverable
      onClick={onClick}
      style={{ marginBottom: 16 }}
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space>
            {getIcon()}
            <div>
              <Text strong>{workflow.task_id}</Text>
              <br />
              <Text type="secondary">
                {taskTypeMap[workflow.task_type] || workflow.task_type}
              </Text>
            </div>
          </Space>
          <StatusBadge status={workflow.status} type="workflow" />
        </Space>

        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Text>目标插件: {workflow.target_plugin}</Text>
          {workflow.health_status && (
            <StatusBadge status={workflow.health_status} type="health" />
          )}
        </Space>

        <Text type="secondary" style={{ fontSize: 12 }}>
          创建时间: {dayjs(workflow.created_at).format('YYYY-MM-DD HH:mm:ss')}
        </Text>
      </Space>
    </Card>
  );
};
