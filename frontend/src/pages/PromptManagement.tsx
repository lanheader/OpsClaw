/**
 * 提示词管理页面
 * 显示所有提示词列表、编辑基础提示词、查看优化历史
 */

import { useState } from 'react';
import {
  Card,
  Table,
  Button,
  Space,
  Tag,
  Typography,
  Modal,
  Form,
  Input,
  message,
  Descriptions,
  Statistic,
  Row,
  Col,
  Alert,
  Select,
  Tooltip,
} from 'antd';
import {
  EditOutlined,
  EyeOutlined,
  HistoryOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  DatabaseOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { promptsApi } from '@/api/prompts';
import type { PromptListItem, PromptDetail, ChangeLog } from '@/api/prompts';
import type { SubagentName, PromptType } from '@/types/prompts';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

export const PromptManagement: React.FC = () => {
  const queryClient = useQueryClient();
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [selectedPrompt, setSelectedPrompt] = useState<PromptDetail | null>(null);
  const [editForm] = Form.useForm();
  const [filterSubagent, setFilterSubagent] = useState<string>('');
  const [filterType, setFilterType] = useState<PromptType | ''>('');

  // 查询统计信息
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['prompt-stats'],
    queryFn: promptsApi.getStats,
    refetchInterval: 30000,
  });

  // 查询提示词列表
  const { data: prompts, isLoading: promptsLoading, refetch: refetchPrompts } = useQuery({
    queryKey: ['prompt-list', filterSubagent, filterType],
    queryFn: () => promptsApi.listPrompts({
      subagent_name: filterSubagent || undefined,
      prompt_type: filterType || undefined,
    }),
  });

  // 查询变更日志
  const { data: changeLogs, isLoading: logsLoading } = useQuery({
    queryKey: ['prompt-logs', filterSubagent],
    queryFn: () => promptsApi.getChangeLogs({
      subagent_name: filterSubagent || undefined,
      limit: 20,
    }),
  });

  // 更新提示词
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: { content: string; notes?: string } }) =>
      promptsApi.updatePrompt(id, data),
    onSuccess: (data) => {
      message.success(data.message);
      queryClient.invalidateQueries({ queryKey: ['prompt-list'] });
      queryClient.invalidateQueries({ queryKey: ['prompt-stats'] });
      setEditModalOpen(false);
      editForm.resetFields();
    },
    onError: (error: any) => {
      message.error(`更新失败: ${error.response?.data?.detail || error.message}`);
    },
  });

  // 查看详情
  const handleViewDetail = async (id: number) => {
    try {
      const detail = await promptsApi.getPromptDetail(id);
      setSelectedPrompt(detail);
      setDetailModalOpen(true);
    } catch (error: any) {
      message.error(`加载详情失败: ${error.response?.data?.detail || error.message}`);
    }
  };

  // 编辑提示词
  const handleEdit = (prompt: PromptListItem) => {
    promptsApi.getPromptDetail(prompt.id).then((detail) => {
      setSelectedPrompt(detail);
      editForm.setFieldsValue({
        content: detail.prompt_content,
        notes: detail.notes || '',
      });
      setEditModalOpen(true);
    });
  };

  // 保存编辑
  const handleSaveEdit = () => {
    if (!selectedPrompt) return;

    editForm.validateFields().then((values) => {
      updateMutation.mutate({
        id: selectedPrompt.id,
        data: {
          content: values.content,
          notes: values.notes,
        },
      });
    });
  };

  // 表格列定义
  const columns = [
    {
      title: 'Subagent',
      dataIndex: 'subagent_name',
      key: 'subagent_name',
      width: 150,
      render: (name: SubagentName) => {
        const config: Record<string, { color: string; icon: string }> = {
          'main-agent': { color: 'blue', icon: '🎯' },
          'data-agent': { color: 'green', icon: '📊' },
          'analyze-agent': { color: 'orange', icon: '🔍' },
          'execute-agent': { color: 'red', icon: '⚡' },
        };
        const cfg = config[name] || { color: 'default', icon: '🤖' };
        return (
          <Tag color={cfg.color}>
            {cfg.icon} {name}
          </Tag>
        );
      },
    },
    {
      title: '版本',
      dataIndex: 'version',
      key: 'version',
      width: 80,
    },
    {
      title: '类型',
      dataIndex: 'prompt_type',
      key: 'prompt_type',
      width: 100,
      render: (type: PromptType) => (
        <Tag color={type === 'base' ? 'blue' : 'green'}>
          {type === 'base' ? '基础' : '优化'}
        </Tag>
      ),
    },
    {
      title: '状态',
      key: 'status',
      width: 120,
      render: (_: any, record: PromptListItem) => (
        <Space size="small">
          {record.is_active && <Tag color="success">激活</Tag>}
          {record.is_latest && <Tag color="processing">最新</Tag>}
        </Space>
      ),
    },
    {
      title: '内容预览',
      dataIndex: 'content_preview',
      key: 'content_preview',
      ellipsis: true,
      render: (preview: string) => (
        <Tooltip title={preview}>
          <Text ellipsis style={{ maxWidth: 300 }}>
            {preview}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: '字符数',
      key: 'length',
      width: 100,
      render: (_: any, record: PromptListItem) => {
        const length = record.content_preview.length;
        return <Text type="secondary">{length} 字符</Text>;
      },
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (date: string) => new Date(date).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      fixed: 'right' as const,
      render: (_: any, record: PromptListItem) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleViewDetail(record.id)}
          >
            查看
          </Button>
          {record.prompt_type === 'base' && (
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record)}
            >
              编辑
            </Button>
          )}
        </Space>
      ),
    },
  ];

  // 变更日志表格列
  const logColumns = [
    {
      title: 'Subagent',
      dataIndex: 'subagent_name',
      key: 'subagent_name',
      width: 120,
    },
    {
      title: '变更类型',
      dataIndex: 'change_type',
      key: 'change_type',
      width: 100,
      render: (type: string) => {
        const config: Record<string, { color: string; text: string }> = {
          create: { color: 'green', text: '创建' },
          update: { color: 'blue', text: '更新' },
          optimize: { color: 'orange', text: '优化' },
          activate: { color: 'purple', text: '激活' },
        };
        const cfg = config[type] || { color: 'default', text: type };
        return <Tag color={cfg.color}>{cfg.text}</Tag>;
      },
    },
    {
      title: '版本变化',
      key: 'version_change',
      width: 150,
      render: (_: any, record: ChangeLog) => (
        <Space size="small">
          {record.old_version && <Text delete>{record.old_version}</Text>}
          <Text>→</Text>
          <Text strong>{record.new_version}</Text>
        </Space>
      ),
    },
    {
      title: '说明',
      dataIndex: 'change_reason',
      key: 'change_reason',
      ellipsis: true,
    },
    {
      title: '时间',
      dataIndex: 'changed_at',
      key: 'changed_at',
      width: 180,
      render: (date: string) => new Date(date).toLocaleString('zh-CN'),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* 页面标题 */}
      <Card>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Title level={2} style={{ margin: 0 }}>
            <FileTextOutlined /> 提示词管理
          </Title>
          <Text type="secondary">管理 AI Subagents 的基础提示词和优化版本</Text>
        </Space>
      </Card>

      {/* 统计卡片 */}
      <Row gutter={16}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="提示词总数"
              value={stats?.total_prompts || 0}
              prefix={<DatabaseOutlined />}
              loading={statsLoading}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="基础版本"
              value={stats?.by_type?.base || 0}
              valueStyle={{ color: '#1890ff' }}
              loading={statsLoading}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="优化版本"
              value={stats?.by_type?.optimized || 0}
              valueStyle={{ color: '#52c41a' }}
              prefix={<ThunderboltOutlined />}
              loading={statsLoading}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Button
              type="primary"
              icon={<ReloadOutlined />}
              onClick={() => refetchPrompts()}
              loading={promptsLoading}
              block
            >
              刷新数据
            </Button>
          </Card>
        </Col>
      </Row>

      {/* 提示词列表 */}
      <Card
        title="提示词列表"
        extra={
          <Space>
            <Select
              placeholder="筛选 Subagent"
              allowClear
              style={{ width: 150 }}
              value={filterSubagent}
              onChange={setFilterSubagent}
              options={[
                { label: 'Main Agent', value: 'main-agent' },
                { label: 'Data Agent', value: 'data-agent' },
                { label: 'Analyze Agent', value: 'analyze-agent' },
                { label: 'Execute Agent', value: 'execute-agent' },
              ]}
            />
            <Select
              placeholder="筛选类型"
              allowClear
              style={{ width: 120 }}
              value={filterType}
              onChange={setFilterType}
              options={[
                { label: '基础版本', value: 'base' },
                { label: '优化版本', value: 'optimized' },
              ]}
            />
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={prompts || []}
          loading={promptsLoading}
          rowKey="id"
          scroll={{ x: 1200 }}
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
          }}
        />
      </Card>

      {/* 变更日志 */}
      <Card
        title={
          <Space>
            <HistoryOutlined />
            变更日志
          </Space>
        }
      >
        <Table
          columns={logColumns}
          dataSource={changeLogs?.logs || []}
          loading={logsLoading}
          rowKey="id"
          pagination={{ pageSize: 10 }}
          expandable={{
            expandedRowRender: (record: ChangeLog) => (
              <Descriptions size="small" column={2}>
                {record.old_content && (
                  <Descriptions.Item label="旧内容预览">
                    <Paragraph ellipsis={{ rows: 2 }}>
                      {record.old_content}
                    </Paragraph>
                  </Descriptions.Item>
                )}
                {record.new_content && (
                  <Descriptions.Item label="新内容预览">
                    <Paragraph ellipsis={{ rows: 2 }}>
                      {record.new_content}
                    </Paragraph>
                  </Descriptions.Item>
                )}
                {record.optimization_method && (
                  <Descriptions.Item label="优化方法">
                    {record.optimization_method}
                  </Descriptions.Item>
                )}
                {record.training_examples_count && (
                  <Descriptions.Item label="训练数据量">
                    {record.training_examples_count} 条
                  </Descriptions.Item>
                )}
              </Descriptions>
            ),
          }}
        />
      </Card>

      {/* 详情弹窗 */}
      <Modal
        title="提示词详情"
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={null}
        width={800}
      >
        {selectedPrompt && (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Descriptions bordered column={2}>
              <Descriptions.Item label="Subagent" span={2}>
                {selectedPrompt.subagent_name}
              </Descriptions.Item>
              <Descriptions.Item label="版本">
                {selectedPrompt.version}
              </Descriptions.Item>
              <Descriptions.Item label="类型">
                <Tag color={selectedPrompt.prompt_type === 'base' ? 'blue' : 'green'}>
                  {selectedPrompt.prompt_type === 'base' ? '基础' : '优化'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="字符数">
                {selectedPrompt.prompt_content.length}
              </Descriptions.Item>
              <Descriptions.Item label="使用次数">
                {selectedPrompt.usage_count}
              </Descriptions.Item>
              {selectedPrompt.optimization_metadata && (
                <>
                  <Descriptions.Item label="优化方法">
                    {selectedPrompt.optimization_metadata.method}
                  </Descriptions.Item>
                  <Descriptions.Item label="训练数据量">
                    {selectedPrompt.optimization_metadata.training_examples_count}
                  </Descriptions.Item>
                </>
              )}
            </Descriptions>

            <Card size="small" title="提示词内容">
              <pre
                style={{
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  maxHeight: 400,
                  overflow: 'auto',
                  backgroundColor: '#f5f5f5',
                  padding: 12,
                  borderRadius: 4,
                }}
              >
                {selectedPrompt.prompt_content}
              </pre>
            </Card>

            {selectedPrompt.notes && (
              <Alert message="备注" description={selectedPrompt.notes} type="info" />
            )}
          </Space>
        )}
      </Modal>

      {/* 编辑弹窗 */}
      <Modal
        title={`编辑提示词 - ${selectedPrompt?.subagent_name}`}
        open={editModalOpen}
        onCancel={() => setEditModalOpen(false)}
        onOk={handleSaveEdit}
        confirmLoading={updateMutation.isPending}
        width={900}
        okText="保存"
      >
        <Form form={editForm} layout="vertical">
          <Form.Item
            label="提示词内容"
            name="content"
            rules={[{ required: true, message: '请输入提示词内容' }]}
          >
            <TextArea
              rows={20}
              placeholder="输入提示词内容..."
              style={{ fontFamily: 'monospace', fontSize: 12 }}
            />
          </Form.Item>

          <Form.Item label="备注说明" name="notes">
            <Input placeholder="简要说明本次修改的原因" />
          </Form.Item>

          <Alert
            message="编辑提示词后"
            description="系统将自动重新生成优化版本，确保 AI Subagents 使用最新的提示词。"
            type="info"
            showIcon
          />
        </Form>
      </Modal>
    </Space>
  );
};

export default PromptManagement;
