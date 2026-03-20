// src/pages/WorkflowExecute.tsx
/**
 * 工作流执行页面
 */
import { useState } from 'react';
import { Card, Form, Select, Input, Button, Space, message, Alert } from 'antd';
import { useMutation } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { workflowAPI } from '@/api/workflow';
import type { WorkflowExecuteRequest } from '@/types/workflow';

export const WorkflowExecute: React.FC = () => {
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const [result, setResult] = useState<any>(null);

  const executeMutation = useMutation({
    mutationFn: (request: WorkflowExecuteRequest) => workflowAPI.execute(request),
    onSuccess: (data) => {
      message.success('工作流已启动');
      setResult(data);
    },
    onError: (error: any) => {
      message.error(error.response?.data?.detail || '执行失败');
    },
  });

  const handleSubmit = (values: WorkflowExecuteRequest) => {
    executeMutation.mutate(values);
  };

  const handleViewStatus = () => {
    if (result?.task_id) {
      navigate(`/workflow/${result.task_id}`);
    }
  };

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card title="执行工作流">
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          initialValues={{
            trigger_source: 'web',
            environment: 'production',
          }}
        >
          <Form.Item
            name="task_type"
            label="任务类型"
            rules={[{ required: true, message: '请选择任务类型' }]}
          >
            <Select placeholder="选择任务类型">
              <Select.Option value="scheduled_inspection">定期巡检</Select.Option>
              <Select.Option value="alert_triggered">告警触发</Select.Option>
              <Select.Option value="manual_command">手动命令</Select.Option>
              <Select.Option value="emergency_response">紧急响应</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="target_plugin"
            label="目标插件"
            rules={[{ required: true, message: '请输入目标插件' }]}
          >
            <Input placeholder="例如: redis-prod, mysql-prod" />
          </Form.Item>

          <Form.Item
            name="trigger_source"
            label="触发源"
          >
            <Select>
              <Select.Option value="web">Web 控制台</Select.Option>
              <Select.Option value="api">API</Select.Option>
              <Select.Option value="scheduler">定时调度</Select.Option>
              <Select.Option value="feishu">飞书</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="trigger_user"
            label="触发用户"
          >
            <Input placeholder="可选" />
          </Form.Item>

          <Form.Item
            name="environment"
            label="环境"
          >
            <Select>
              <Select.Option value="production">生产环境</Select.Option>
              <Select.Option value="staging">预发布</Select.Option>
              <Select.Option value="development">开发环境</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item>
            <Space>
              <Button
                type="primary"
                htmlType="submit"
                loading={executeMutation.isPending}
              >
                执行工作流
              </Button>
              <Button onClick={() => form.resetFields()}>
                重置
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      {result && (
        <Card title="执行结果">
          <Space direction="vertical" style={{ width: '100%' }}>
            <Alert
              message={result.message}
              type={result.success ? 'success' : 'warning'}
              showIcon
            />

            <div>
              <strong>任务 ID:</strong> {result.task_id}
            </div>
            <div>
              <strong>状态:</strong> {result.status}
            </div>
            <div>
              <strong>当前步骤:</strong> {result.current_step}
            </div>
            {result.needs_approval && (
              <Alert
                message="此工作流需要人工审批"
                description="请在飞书中查看审批请求并做出决策"
                type="warning"
                showIcon
              />
            )}

            <Button type="primary" onClick={handleViewStatus}>
              查看详细状态
            </Button>
          </Space>
        </Card>
      )}
    </Space>
  );
};
