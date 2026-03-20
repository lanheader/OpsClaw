// src/pages/WorkflowDetail.tsx
/**
 * 工作流详情页面
 */
import { Card, Descriptions, Space, Button, Timeline, Alert, Tag } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { workflowAPI } from '@/api/workflow';
import { StatusBadge } from '@/components/StatusBadge';

export const WorkflowDetail: React.FC = () => {
  const { taskId } = useParams<{ taskId: string }>();

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['workflow-status', taskId],
    queryFn: () => workflowAPI.getStatus(taskId!),
    enabled: !!taskId,
    refetchInterval: (query) => {
      // 如果状态是运行中或等待审批，每5秒刷新一次
      if (query.state.data?.status === 'running' || query.state.data?.status === 'paused_approval') {
        return 5000;
      }
      return false;
    },
  });

  if (!taskId) {
    return <Alert message="缺少任务 ID" type="error" />;
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card
        title={`工作流详情: ${taskId}`}
        extra={
          <Button
            icon={<ReloadOutlined />}
            onClick={() => refetch()}
            loading={isLoading}
          >
            刷新
          </Button>
        }
        loading={isLoading}
      >
        {data && (
          <>
            <Descriptions column={2} bordered>
              <Descriptions.Item label="任务 ID">{data.task_id}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <StatusBadge status={data.status} type="workflow" />
              </Descriptions.Item>
              <Descriptions.Item label="当前步骤">{data.current_step}</Descriptions.Item>
              <Descriptions.Item label="健康状态">
                {data.health_status ? (
                  <StatusBadge status={data.health_status} type="health" />
                ) : (
                  '未知'
                )}
              </Descriptions.Item>
              <Descriptions.Item label="需要审批">
                {data.needs_approval ? (
                  <Tag color="warning">是</Tag>
                ) : (
                  <Tag>否</Tag>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="审批状态">
                {data.approval_status || '无'}
              </Descriptions.Item>
              <Descriptions.Item label="执行结果" span={2}>
                {data.success !== undefined ? (
                  data.success ? (
                    <Tag color="success">成功</Tag>
                  ) : (
                    <Tag color="error">失败</Tag>
                  )
                ) : (
                  '执行中'
                )}
              </Descriptions.Item>
            </Descriptions>

            {data.needs_approval && !data.approval_status && (
              <Alert
                message="等待审批"
                description="此工作流正在等待人工审批，请在飞书中查看审批请求"
                type="warning"
                showIcon
                style={{ marginTop: 16 }}
              />
            )}
          </>
        )}
      </Card>

      {data?.messages && data.messages.length > 0 && (
        <Card title="执行日志">
          <Timeline
            items={data.messages.map((msg, index) => ({
              key: index,
              children: (
                <div>
                  <Tag>{msg.role}</Tag>
                  <span style={{ marginLeft: 8 }}>{msg.content}</span>
                </div>
              ),
            }))}
          />
        </Card>
      )}
    </Space>
  );
};
