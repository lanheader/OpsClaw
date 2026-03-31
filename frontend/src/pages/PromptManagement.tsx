// src/pages/PromptManagement.tsx
/**
 * 提示词管理页面
 */

import React, { useState } from 'react';
import {
  Card,
  Table,
  Button,
  Space,
  Modal,
  Form,
  Input,
  message,
  Typography,
  Tag,
  Drawer,
  List,
  Popconfirm,
  Spin,
  Tooltip,
  Badge,
} from 'antd';
import {
  EditOutlined,
  HistoryOutlined,
  RollbackOutlined,
  ClearOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  promptsApi,
  AgentPrompt,
  AgentPromptListItem,
  AgentPromptUpdate,
  AgentPromptCreate,
  PromptVersionListItem,
} from '../api/prompts';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const PromptManagement: React.FC = () => {
  const queryClient = useQueryClient();

  // 状态管理
  const [editingPrompt, setEditingPrompt] = useState<AgentPrompt | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [versionDrawer, setVersionDrawer] = useState<{ visible: boolean; agentName: string }>({
    visible: false,
    agentName: '',
  });
  const [editForm] = Form.useForm();
  const [createForm] = Form.useForm();

  // 查询提示词列表
  const { data: prompts, isLoading } = useQuery({
    queryKey: ['prompts'],
    queryFn: promptsApi.getAll,
  });

  // 查询版本历史
  const { data: versions, isLoading: versionsLoading } = useQuery({
    queryKey: ['prompt-versions', versionDrawer.agentName],
    queryFn: () => promptsApi.getVersions(versionDrawer.agentName),
    enabled: versionDrawer.visible,
  });

  // 创建提示词
  const createMutation = useMutation({
    mutationFn: (data: AgentPromptCreate) => promptsApi.create(data),
    onSuccess: () => {
      message.success('提示词创建成功');
      setIsCreateModalOpen(false);
      createForm.resetFields();
      queryClient.invalidateQueries({ queryKey: ['prompts'] });
    },
    onError: (error: any) => {
      message.error(`创建失败: ${error.response?.data?.detail || error.message}`);
    },
  });

  // 更新提示词
  const updateMutation = useMutation({
    mutationFn: ({ agentName, data }: { agentName: string; data: AgentPromptUpdate }) =>
      promptsApi.update(agentName, data),
    onSuccess: () => {
      message.success('提示词更新成功');
      setEditingPrompt(null);
      queryClient.invalidateQueries({ queryKey: ['prompts'] });
    },
    onError: (error: any) => {
      message.error(`更新失败: ${error.response?.data?.detail || error.message}`);
    },
  });

  // 回滚提示词
  const rollbackMutation = useMutation({
    mutationFn: ({ agentName, targetVersion }: { agentName: string; targetVersion: number }) =>
      promptsApi.rollback(agentName, targetVersion),
    onSuccess: (data) => {
      message.success(data.message);
      setVersionDrawer({ visible: false, agentName: '' });
      queryClient.invalidateQueries({ queryKey: ['prompts'] });
    },
    onError: (error: any) => {
      message.error(`回滚失败: ${error.response?.data?.detail || error.message}`);
    },
  });

  // 清除缓存
  const clearCacheMutation = useMutation({
    mutationFn: promptsApi.clearCache,
    onSuccess: (data) => {
      message.success(data.message);
    },
    onError: (error: any) => {
      message.error(`清除缓存失败: ${error.response?.data?.detail || error.message}`);
    },
  });

  // 表格列定义
  const columns = [
    {
      title: 'Agent',
      dataIndex: 'agent_name',
      key: 'agent_name',
      width: 150,
      render: (text: string) => (
        <Tag color="blue" style={{ fontFamily: 'monospace' }}>{text}</Tag>
      ),
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 180,
    },
    {
      title: '版本',
      dataIndex: 'version',
      key: 'version',
      width: 80,
      render: (version: number) => (
        <Badge count={`v${version}`} style={{ backgroundColor: '#52c41a' }} />
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 80,
      render: (isActive: boolean) => (
        <Tag color={isActive ? 'success' : 'default'}>
          {isActive ? '激活' : '未激活'}
        </Tag>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '最后更新',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (date: string) => new Date(date).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: any, record: AgentPromptListItem) => (
        <Space>
          <Tooltip title="编辑">
            <Button
              type="primary"
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record)}
            >
              编辑
            </Button>
          </Tooltip>
          <Tooltip title="版本历史">
            <Button
              size="small"
              icon={<HistoryOutlined />}
              onClick={() => setVersionDrawer({ visible: true, agentName: record.agent_name })}
            >
              历史
            </Button>
          </Tooltip>
        </Space>
      ),
    },
  ];

  // 编辑提示词
  const handleEdit = async (record: AgentPromptListItem) => {
    try {
      const fullPrompt = await promptsApi.getByName(record.agent_name);
      setEditingPrompt(fullPrompt);
      editForm.setFieldsValue({
        name: fullPrompt.name,
        description: fullPrompt.description,
        content: fullPrompt.content,
        is_active: fullPrompt.is_active,
      });
    } catch (error) {
      message.error('加载提示词失败');
    }
  };

  // 保存编辑
  const handleSaveEdit = async () => {
    if (!editingPrompt) return;

    try {
      const values = await editForm.validateFields();
      updateMutation.mutate({
        agentName: editingPrompt.agent_name,
        data: values,
      });
    } catch (error) {
      // Form validation error
    }
  };

  // 创建提示词
  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields();
      createMutation.mutate(values);
    } catch (error) {
      // Form validation error
    }
  };

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* 操作栏 */}
      <Card>
        <Space>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setIsCreateModalOpen(true)}
          >
            新建提示词
          </Button>
          <Popconfirm
            title="清除所有提示词缓存"
            description="这将清除内存中的提示词缓存，下次请求将从数据库重新加载。确定继续？"
            onConfirm={() => clearCacheMutation.mutate()}
          >
            <Button
              icon={<ClearOutlined />}
              loading={clearCacheMutation.isPending}
            >
              清除缓存
            </Button>
          </Popconfirm>
        </Space>
      </Card>

      {/* 提示词列表 */}
      <Card title="提示词管理">
        <Table
          columns={columns}
          dataSource={prompts}
          loading={isLoading}
          rowKey="id"
          pagination={{ pageSize: 10 }}
        />
      </Card>

      {/* 创建 Modal */}
      <Modal
        title="新建提示词"
        open={isCreateModalOpen}
        onCancel={() => {
          setIsCreateModalOpen(false);
          createForm.resetFields();
        }}
        width={1000}
        footer={[
          <Button key="cancel" onClick={() => {
            setIsCreateModalOpen(false);
            createForm.resetFields();
          }}>
            取消
          </Button>,
          <Button
            key="submit"
            type="primary"
            onClick={handleCreate}
            loading={createMutation.isPending}
          >
            创建
          </Button>,
        ]}
      >
        <Form
          form={createForm}
          layout="vertical"
        >
          <Form.Item
            label="Agent 标识符"
            name="agent_name"
            rules={[{ required: true, message: '请输入 Agent 标识符' }]}
          >
            <Input placeholder="例如: data-agent, analyze-agent, execute-agent, main-agent" />
          </Form.Item>
          <Form.Item
            label="显示名称"
            name="name"
            rules={[{ required: true, message: '请输入显示名称' }]}
          >
            <Input placeholder="例如: 数据采集智能体" />
          </Form.Item>
          <Form.Item label="描述" name="description">
            <TextArea rows={2} placeholder="描述这个提示词的用途" />
          </Form.Item>
          <Form.Item
            label="提示词内容"
            name="content"
            rules={[{ required: true, message: '请输入提示词内容' }]}
          >
            <TextArea
              rows={20}
              style={{ fontFamily: 'monospace', fontSize: '13px' }}
              placeholder="输入提示词内容..."
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑 Modal */}
      <Modal
        title={`编辑提示词 - ${editingPrompt?.name || ''}`}
        open={!!editingPrompt}
        onCancel={() => {
          setEditingPrompt(null);
          editForm.resetFields();
        }}
        width={1000}
        footer={[
          <Button key="cancel" onClick={() => {
            setEditingPrompt(null);
            editForm.resetFields();
          }}>
            取消
          </Button>,
          <Button
            key="submit"
            type="primary"
            onClick={handleSaveEdit}
            loading={updateMutation.isPending}
          >
            保存
          </Button>,
        ]}
      >
        <Form
          form={editForm}
          layout="vertical"
        >
          <Form.Item label="名称" name="name">
            <Input />
          </Form.Item>
          <Form.Item label="描述" name="description">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item
            label="提示词内容"
            name="content"
            rules={[{ required: true, message: '请输入提示词内容' }]}
          >
            <TextArea
              rows={20}
              style={{ fontFamily: 'monospace', fontSize: '13px' }}
              placeholder="输入提示词内容..."
            />
          </Form.Item>
          <Form.Item label="激活状态" name="is_active" valuePropName="checked">
            <Tag color="blue">激活中的提示词才会被 Agent 使用</Tag>
          </Form.Item>
        </Form>
      </Modal>

      {/* 版本历史抽屉 */}
      <Drawer
        title={`版本历史 - ${versionDrawer.agentName}`}
        placement="right"
        width={600}
        open={versionDrawer.visible}
        onClose={() => setVersionDrawer({ visible: false, agentName: '' })}
      >
        <Spin spinning={versionsLoading}>
          <List
            dataSource={versions}
            renderItem={(version: PromptVersionListItem) => (
              <List.Item
                actions={[
                  <Popconfirm
                    key="rollback"
                    title="确定回滚到此版本？"
                    description="回滚后，当前内容将被替换为该版本的内容。"
                    onConfirm={() => {
                      rollbackMutation.mutate({
                        agentName: versionDrawer.agentName,
                        targetVersion: version.version,
                      });
                    }}
                  >
                    <Button
                      size="small"
                      icon={<RollbackOutlined />}
                      loading={rollbackMutation.isPending}
                    >
                      回滚
                    </Button>
                  </Popconfirm>,
                ]}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Badge count={`v${version.version}`} style={{ backgroundColor: '#1890ff' }} />
                      {version.change_summary && (
                        <Text type="secondary">{version.change_summary}</Text>
                      )}
                    </Space>
                  }
                  description={
                    <Space direction="vertical" size="small">
                      <Text type="secondary">
                        {version.changed_by} - {new Date(version.created_at).toLocaleString('zh-CN')}
                      </Text>
                      <Paragraph
                        ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}
                        style={{ marginBottom: 0, color: '#666' }}
                      >
                        {version.content_preview}
                      </Paragraph>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        </Spin>
      </Drawer>
    </Space>
  );
};

export default PromptManagement;
