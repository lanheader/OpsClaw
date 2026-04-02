import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Table,
  Button,
  Space,
  Tag,
  Switch,
  Modal,
  Form,
  Input,
  Select,
  InputNumber,
  message,
  Popconfirm,
  Statistic,
  Row,
  Col,
  Tooltip,
  Progress,
  Typography,
} from 'antd';
import {
  PlusOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  DeleteOutlined,
  EditOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  LoadingOutlined,
  ExclamationCircleOutlined,
  HistoryOutlined,
} from '@ant-design/icons';
import {
  scheduledTasksApi,
  ScheduledTask,
  TaskExecution,
  TaskStats,
  TaskCreate,
} from '../api/scheduledTasks';

const { Text } = Typography;
const { TextArea } = Input;

const TASK_TYPE_MAP: Record<string, { label: string; color: string }> = {
  k8s_inspect: { label: 'K8s 巡检', color: 'blue' },
  resource_report: { label: '资源报告', color: 'green' },
  pod_restart: { label: 'Pod 重启检测', color: 'orange' },
  custom_command: { label: '自定义命令', color: 'purple' },
  webhook: { label: 'Webhook', color: 'cyan' },
};

const STATUS_MAP: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  pending: { label: '等待中', color: 'default', icon: <ClockCircleOutlined /> },
  running: { label: '执行中', color: 'processing', icon: <LoadingOutlined /> },
  success: { label: '成功', color: 'success', icon: <CheckCircleOutlined /> },
  failed: { label: '失败', color: 'error', icon: <CloseCircleOutlined /> },
  timeout: { label: '超时', color: 'warning', icon: <ExclamationCircleOutlined /> },
};

const ScheduledTasks: React.FC = () => {
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [stats, setStats] = useState<TaskStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<ScheduledTask | null>(null);
  const [form] = Form.useForm();
  const [execModalOpen, setExecModalOpen] = useState(false);
  const [execTaskId, setExecTaskId] = useState<number | null>(null);
  const [executions, setExecutions] = useState<TaskExecution[]>([]);
  const [execLoading, setExecLoading] = useState(false);
  const [execTotal, setExecTotal] = useState(0);
  const [execPage, setExecPage] = useState(1);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const res = await scheduledTasksApi.getTasks(1, 100);
      setTasks(res.items);
    } catch {
      message.error('加载任务列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadStats = useCallback(async () => {
    try {
      const data = await scheduledTasksApi.getStats();
      setStats(data);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    loadTasks();
    loadStats();
  }, [loadTasks, loadStats]);

  const handleCreate = () => {
    setEditingTask(null);
    form.resetFields();
    form.setFieldsValue({
      task_type: 'k8s_inspect',
      timezone: 'Asia/Shanghai',
      timeout: 600,
      cron_expr: '0 8 * * *',
      enabled: true,
    });
    setModalOpen(true);
  };

  const handleEdit = (task: ScheduledTask) => {
    setEditingTask(task);
    form.setFieldsValue({
      ...task,
      task_params: task.task_params || '',
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      if (editingTask) {
        await scheduledTasksApi.updateTask(editingTask.id, values);
        message.success('任务已更新');
      } else {
        await scheduledTasksApi.createTask(values as TaskCreate);
        message.success('任务已创建');
      }
      setModalOpen(false);
      loadTasks();
      loadStats();
    } catch {
      // validation error
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await scheduledTasksApi.deleteTask(id);
      message.success('任务已删除');
      loadTasks();
      loadStats();
    } catch {
      message.error('删除失败');
    }
  };

  const handleToggle = async (id: number, enabled: boolean) => {
    try {
      await scheduledTasksApi.toggleTask(id);
      message.success(enabled ? '任务已禁用' : '任务已启用');
      loadTasks();
      loadStats();
    } catch {
      message.error('操作失败');
    }
  };

  const handleRun = async (id: number) => {
    try {
      await scheduledTasksApi.runTask(id);
      message.success('任务已触发');
      setTimeout(loadStats, 2000);
    } catch {
      message.error('触发失败');
    }
  };

  const showExecutions = (taskId: number) => {
    setExecTaskId(taskId);
    setExecPage(1);
    setExecModalOpen(true);
  };

  const loadExecutions = async (taskId: number, page: number) => {
    setExecLoading(true);
    try {
      const res = await scheduledTasksApi.getTaskExecutions(taskId, page, 10);
      setExecutions(res.items);
      setExecTotal(res.total);
    } catch {
      message.error('加载执行记录失败');
    } finally {
      setExecLoading(false);
    }
  };

  useEffect(() => {
    if (execTaskId !== null) {
      loadExecutions(execTaskId, execPage);
    }
  }, [execTaskId, execPage]);

  const successRate = stats
    ? stats.today_stats.total > 0
      ? Math.round((stats.today_stats.success / stats.today_stats.total) * 100)
      : 0
    : 0;

  const taskColumns = [
    {
      title: '任务名称',
      dataIndex: 'name',
      key: 'name',
      width: 160,
      ellipsis: true,
    },
    {
      title: '类型',
      dataIndex: 'task_type',
      key: 'task_type',
      width: 120,
      render: (type: string) => {
        const info = TASK_TYPE_MAP[type] || { label: type, color: 'default' };
        return <Tag color={info.color}>{info.label}</Tag>;
      },
    },
    {
      title: 'Cron',
      dataIndex: 'cron_expr',
      key: 'cron_expr',
      width: 140,
      render: (val: string) => <Text code>{val}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (enabled: boolean, record: ScheduledTask) => (
        <Switch
          size="small"
          checked={enabled}
          onChange={(val) => handleToggle(record.id, val)}
        />
      ),
    },
    {
      title: '超时(秒)',
      dataIndex: 'timeout',
      key: 'timeout',
      width: 90,
      render: (val: number) => val ? `${val}s` : '-',
    },
    {
      title: '失败通知',
      dataIndex: 'notify_on_fail',
      key: 'notify_on_fail',
      width: 90,
      render: (val: boolean) => val ? <Tag color="warning">是</Tag> : '-',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (val: string) => val ? new Date(val).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: any, record: ScheduledTask) => (
        <Space size="small">
          <Tooltip title="立即执行">
            <Button
              size="small"
              type="primary"
              icon={<PlayCircleOutlined />}
              disabled={!record.enabled}
              onClick={() => handleRun(record.id)}
            />
          </Tooltip>
          <Tooltip title="执行记录">
            <Button
              size="small"
              icon={<HistoryOutlined />}
              onClick={() => showExecutions(record.id)}
            />
          </Tooltip>
          <Tooltip title="编辑">
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record)}
            />
          </Tooltip>
          <Popconfirm title="确定删除此任务？" onConfirm={() => handleDelete(record.id)}>
            <Tooltip title="删除">
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const execColumns = [
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) => {
        const info = STATUS_MAP[status] || { label: status, color: 'default', icon: null };
        return <Tag icon={info.icon} color={info.color}>{info.label}</Tag>;
      },
    },
    {
      title: '触发方式',
      dataIndex: 'trigger_type',
      key: 'trigger_type',
      width: 90,
      render: (type: string) => (
        <Tag color={type === 'manual' ? 'blue' : 'default'}>
          {type === 'manual' ? '手动' : '定时'}
        </Tag>
      ),
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      width: 170,
      render: (val: string) => val ? new Date(val).toLocaleString('zh-CN') : '-',
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      width: 100,
      render: (val: number | null) => {
        if (val === null || val === undefined) return '-';
        if (val < 1000) return `${val}ms`;
        return `${(val / 1000).toFixed(1)}s`;
      },
    },
    {
      title: '结果',
      dataIndex: 'result_summary',
      key: 'result_summary',
      ellipsis: true,
      render: (val: string | null, record: TaskExecution) => (
        <Tooltip title={record.error_message || val || '-'}>
          <Text style={{ maxWidth: 200 }} ellipsis>
            {record.error_message || val || '-'}
          </Text>
        </Tooltip>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* 统计卡片 */}
      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic title="总任务数" value={stats?.total ?? 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="已启用" value={stats?.enabled ?? 0} valueStyle={{ color: '#1890ff' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="今日执行" value={stats?.today_stats?.total ?? 0} suffix={`/ ${stats?.today_stats?.running ?? 0} 执行中`} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="今日成功率"
              value={successRate}
              suffix="%"
              valueStyle={{ color: successRate >= 90 ? '#52c41a' : successRate >= 70 ? '#faad14' : '#ff4d4f' }}
              prefix={stats?.today_stats?.total ? <Progress percent={successRate} size="small" showInfo={false} style={{ width: 60 }} /> : null}
            />
          </Card>
        </Col>
      </Row>

      {/* 任务列表 */}
      <Card
        title="定时任务"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => { loadTasks(); loadStats(); }}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
              新建任务
            </Button>
          </Space>
        }
      >
        <Table
          dataSource={tasks}
          columns={taskColumns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          size="middle"
        />
      </Card>

      {/* 新建/编辑弹窗 */}
      <Modal
        title={editingTask ? '编辑任务' : '新建任务'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        width={600}
        destroyOnClose
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item name="name" label="任务名称" rules={[{ required: true, message: '请输入任务名称' }]}>
            <Input placeholder="如：每日集群巡检" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input placeholder="任务描述（可选）" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="task_type" label="任务类型" rules={[{ required: true }]}>
                <Select>
                  {Object.entries(TASK_TYPE_MAP).map(([key, { label }]) => (
                    <Select.Option key={key} value={key}>{label}</Select.Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="cron_expr" label="Cron 表达式" rules={[{ required: true, message: '请输入 Cron 表达式' }]}>
                <Input placeholder="0 8 * * *" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="timezone" label="时区">
                <Select>
                  <Select.Option value="Asia/Shanghai">Asia/Shanghai (北京时间)</Select.Option>
                  <Select.Option value="UTC">UTC</Select.Option>
                  <Select.Option value="America/New_York">America/New_York</Select.Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="timeout" label="超时时间（秒）">
                <InputNumber min={60} max={3600} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="task_params" label="任务参数（JSON）">
            <TextArea rows={4} placeholder='{"namespace": "default"}' style={{ fontFamily: 'monospace' }} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="enabled" label="启用" valuePropName="checked">
                <Switch checkedChildren="启用" unCheckedChildren="禁用" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="notify_on_fail" label="失败通知" valuePropName="checked">
                <Switch checkedChildren="是" unCheckedChildren="否" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="notify_target" label="通知目标">
                <Input placeholder="飞书 user_id 或 chat_id" />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* 执行记录弹窗 */}
      <Modal
        title="执行记录"
        open={execModalOpen}
        onCancel={() => setExecModalOpen(false)}
        footer={null}
        width={800}
      >
        <Table
          dataSource={executions}
          columns={execColumns}
          rowKey="id"
          loading={execLoading}
          size="small"
          pagination={{
            current: execPage,
            total: execTotal,
            pageSize: 10,
            onChange: setExecPage,
            showSizeChanger: false,
          }}
        />
      </Modal>
    </Space>
  );
};

export default ScheduledTasks;
