// src/pages/KnowledgeManagement.tsx
/**
 * 知识库管理页面
 *
 * 功能：
 * - 知识库列表（分页、筛选）
 * - 搜索（关键词）
 * - 新增/编辑/查看详情（Modal 表单）
 * - 删除（软删除，需确认）
 * - 统计概览
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Table,
  Button,
  Space,
  Modal,
  Form,
  Input,
  Select,
  Slider,
  Tag,
  Popconfirm,
  message,
  Typography,
  Row,
  Col,
  Statistic,
  Tooltip,
  Descriptions,
  Badge,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  SearchOutlined,
  EyeOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  DatabaseOutlined,
  BookOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
  KnowledgeItem,
  KnowledgeStats,
  getKnowledgeList,
  searchKnowledge,
  getKnowledgeDetail,
  createKnowledge,
  updateKnowledge,
  deleteKnowledge,
  getKnowledgeStats,
} from '@/api/knowledge';

const { Text } = Typography;
const { TextArea } = Input;

const CATEGORY_OPTIONS = [
  { label: 'Kubernetes', value: 'kubernetes' },
  { label: '网络', value: 'network' },
  { label: '存储', value: 'storage' },
  { label: '应用', value: 'application' },
  { label: '数据库', value: 'database' },
  { label: '其他', value: 'other' },
];

const SEVERITY_OPTIONS = [
  { label: '低', value: 'low', color: 'green' },
  { label: '中', value: 'medium', color: 'orange' },
  { label: '高', value: 'high', color: 'red' },
  { label: '严重', value: 'critical', color: 'volcano' },
];

const SEVERITY_TAG_MAP: Record<string, string> = {
  low: 'green',
  medium: 'orange',
  high: 'red',
  critical: 'volcano',
};

const KnowledgeManagement: React.FC = () => {
  const [data, setData] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<KnowledgeStats | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [filterCategory, setFilterCategory] = useState<string | undefined>();
  const [filterSeverity, setFilterSeverity] = useState<string | undefined>();

  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });

  const [formModalOpen, setFormModalOpen] = useState(false);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<KnowledgeItem | null>(null);
  const [detailItem, setDetailItem] = useState<KnowledgeItem | null>(null);
  const [formLoading, setFormLoading] = useState(false);

  const [form] = Form.useForm();

  const loadStats = useCallback(async () => {
    try {
      const result = await getKnowledgeStats();
      setStats(result);
    } catch (err) {
      console.error('加载统计失败:', err);
    }
  }, []);

  const loadData = useCallback(async (page = 1, pageSize = 20) => {
    setLoading(true);
    try {
      let items: KnowledgeItem[];
      if (searchQuery.trim()) {
        items = await searchKnowledge(searchQuery, {
          category: filterCategory,
          severity: filterSeverity,
          limit: 100,
        });
      } else {
        items = await getKnowledgeList({
          category: filterCategory,
          severity: filterSeverity,
          limit: pageSize,
          offset: (page - 1) * pageSize,
        });
      }
      setData(items);
      setPagination((prev) => ({ ...prev, current: page, total: items.length }));
    } catch (err) {
      console.error('加载知识库失败:', err);
    } finally {
      setLoading(false);
    }
  }, [searchQuery, filterCategory, filterSeverity]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useEffect(() => {
    loadData(1, pagination.pageSize);
  }, [searchQuery, filterCategory, filterSeverity]);

  const handleSearch = (value: string) => {
    setSearchQuery(value);
  };

  const handleCreate = () => {
    setEditingItem(null);
    form.resetFields();
    form.setFieldsValue({ effectiveness_score: 0.5, severity: 'medium' });
    setFormModalOpen(true);
  };

  const handleEdit = (record: KnowledgeItem) => {
    setEditingItem(record);
    form.setFieldsValue({
      issue_title: record.issue_title,
      issue_description: record.issue_description,
      symptoms: record.symptoms || '',
      root_cause: record.root_cause || '',
      solution: record.solution || '',
      effectiveness_score: record.effectiveness_score,
      severity: record.severity || 'medium',
      affected_system: record.affected_system || '',
      category: record.category || '',
      tags: record.tags || '',
    });
    setFormModalOpen(true);
  };

  const handleView = async (id: number) => {
    try {
      const item = await getKnowledgeDetail(id);
      setDetailItem(item);
      setDetailModalOpen(true);
    } catch (err) {
      message.error('获取详情失败');
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setFormLoading(true);
      if (editingItem) {
        await updateKnowledge(editingItem.id, values);
        message.success('更新成功');
      } else {
        await createKnowledge(values);
        message.success('创建成功');
      }
      setFormModalOpen(false);
      form.resetFields();
      loadData(pagination.current, pagination.pageSize);
      loadStats();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error(editingItem ? '更新失败' : '创建失败');
    } finally {
      setFormLoading(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteKnowledge(id);
      message.success('删除成功');
      loadData(pagination.current, pagination.pageSize);
      loadStats();
    } catch (err) {
      message.error('删除失败');
    }
  };

  const columns: ColumnsType<KnowledgeItem> = [
    {
      title: '标题',
      dataIndex: 'issue_title',
      key: 'issue_title',
      width: 200,
      ellipsis: true,
      render: (text: string, record: KnowledgeItem) => (
        <a onClick={() => handleView(record.id)}>{text}</a>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 100,
      render: (cat: string) => {
        const opt = CATEGORY_OPTIONS.find((o) => o.value === cat);
        return opt ? <Tag>{opt.label}</Tag> : <Text type="secondary">-</Text>;
      },
    },
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      width: 90,
      render: (sev: string) => {
        const opt = SEVERITY_OPTIONS.find((o) => o.value === sev);
        const color = SEVERITY_TAG_MAP[sev] || 'default';
        return opt ? <Tag color={color}>{opt.label}</Tag> : <Text type="secondary">-</Text>;
      },
    },
    {
      title: '有效性',
      dataIndex: 'effectiveness_score',
      key: 'effectiveness_score',
      width: 80,
      render: (score: number) => (
        <Tooltip title={`有效性评分: ${score}`}>
          <Tag color={score >= 0.8 ? 'green' : score >= 0.5 ? 'orange' : 'red'}>
            {Math.round(score * 100)}%
          </Tag>
        </Tooltip>
      ),
    },
    {
      title: '受影响系统',
      dataIndex: 'affected_system',
      key: 'affected_system',
      width: 120,
      ellipsis: true,
      render: (text: string) => text || <Text type="secondary">-</Text>,
    },
    {
      title: '已验证',
      dataIndex: 'is_verified',
      key: 'is_verified',
      width: 80,
      render: (verified: boolean) =>
        verified ? <Badge status="success" text="是" /> : <Badge status="default" text="否" />,
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      width: 150,
      ellipsis: true,
      render: (tags: string) =>
        tags
          ? tags.split(',').map((t) => t.trim()).filter(Boolean).map((t) => <Tag key={t}>{t}</Tag>)
          : <Text type="secondary">-</Text>,
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 160,
      render: (date: string) => new Date(date).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      fixed: 'right' as const,
      render: (_: any, record: KnowledgeItem) => (
        <Space size="small">
          <Tooltip title="查看详情">
            <Button type="text" size="small" icon={<EyeOutlined />} onClick={() => handleView(record.id)} />
          </Tooltip>
          <Tooltip title="编辑">
            <Button type="text" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          </Tooltip>
          <Popconfirm
            title="确认删除"
            description="删除后可通过数据库恢复"
            onConfirm={() => handleDelete(record.id)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Tooltip title="删除">
              <Button type="text" size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 0 }}>
      {stats && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="知识库总数"
                value={stats.total_incidents}
                prefix={<BookOutlined />}
                valueStyle={{ color: '#1890ff' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="已验证"
                value={stats.verified_incidents}
                prefix={<CheckCircleOutlined />}
                valueStyle={{ color: '#52c41a' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="未验证"
                value={stats.total_incidents - stats.verified_incidents}
                prefix={<ExclamationCircleOutlined />}
                valueStyle={{ color: '#faad14' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="分类数"
                value={Object.keys(stats.by_category).length}
                prefix={<DatabaseOutlined />}
                valueStyle={{ color: '#722ed1' }}
              />
            </Card>
          </Col>
        </Row>
      )}

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space wrap>
            <Input.Search
              placeholder="搜索标题、描述、症状、根因、方案..."
              allowClear
              onSearch={handleSearch}
              style={{ width: 320 }}
              enterButton={<SearchOutlined />}
            />
            <Select
              placeholder="分类筛选"
              allowClear
              style={{ width: 140 }}
              value={filterCategory}
              onChange={(val) => setFilterCategory(val)}
              options={CATEGORY_OPTIONS}
            />
            <Select
              placeholder="严重程度"
              allowClear
              style={{ width: 120 }}
              value={filterSeverity}
              onChange={(val) => setFilterSeverity(val)}
              options={SEVERITY_OPTIONS}
            />
          </Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新增知识
          </Button>
        </Space>
      </Card>

      <Card size="small">
        <Table
          columns={columns}
          dataSource={data}
          rowKey="id"
          loading={loading}
          scroll={{ x: 1200 }}
          pagination={{
            ...pagination,
            showTotal: (total) => `共 ${total} 条`,
            showSizeChanger: false,
          }}
          size="middle"
        />
      </Card>

      <Modal
        title={editingItem ? '编辑知识' : '新增知识'}
        open={formModalOpen}
        onOk={handleSubmit}
        onCancel={() => {
          setFormModalOpen(false);
          form.resetFields();
        }}
        confirmLoading={formLoading}
        width={720}
        destroyOnClose
      >
        <Form form={form} layout="vertical" size="middle">
          <Form.Item
            label="问题标题"
            name="issue_title"
            rules={[{ required: true, message: '请输入问题标题' }]}
          >
            <Input placeholder="例：Pod OOMKilled 导致 CrashLoopBackOff" />
          </Form.Item>

          <Form.Item
            label="问题描述"
            name="issue_description"
            rules={[{ required: true, message: '请输入问题描述' }]}
          >
            <TextArea rows={3} placeholder="详细描述问题的表现和现象" />
          </Form.Item>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="分类" name="category">
                <Select placeholder="选择分类" options={CATEGORY_OPTIONS} allowClear />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="严重程度" name="severity">
                <Select placeholder="选择严重程度" options={SEVERITY_OPTIONS} />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item label="症状" name="symptoms">
            <TextArea rows={2} placeholder="观察到的主要症状" />
          </Form.Item>

          <Form.Item label="根本原因" name="root_cause">
            <TextArea rows={2} placeholder="问题的根本原因分析" />
          </Form.Item>

          <Form.Item label="解决方案" name="solution">
            <TextArea rows={3} placeholder="详细的解决步骤和方案" />
          </Form.Item>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="受影响系统" name="affected_system">
                <Input placeholder="例：order-service, payment-api" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="标签（逗号分隔）" name="tags">
                <Input placeholder="例：k8s,oom,memory" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            label={`有效性评分: ${form.getFieldValue('effectiveness_score') ?? 0.5}`}
            name="effectiveness_score"
          >
            <Slider min={0} max={1} step={0.1} marks={{ 0: '低', 0.5: '中', 1: '高' }} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="知识详情"
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button
            key="edit"
            type="primary"
            icon={<EditOutlined />}
            onClick={() => {
              if (detailItem) {
                setDetailModalOpen(false);
                handleEdit(detailItem);
              }
            }}
          >
            编辑
          </Button>,
          <Button key="close" onClick={() => setDetailModalOpen(false)}>
            关闭
          </Button>,
        ]}
        width={720}
      >
        {detailItem && (
          <Descriptions bordered column={1} size="small">
            <Descriptions.Item label="问题标题">{detailItem.issue_title}</Descriptions.Item>
            <Descriptions.Item label="问题描述">{detailItem.issue_description}</Descriptions.Item>
            <Descriptions.Item label="分类">
              {CATEGORY_OPTIONS.find((o) => o.value === detailItem.category)?.label ||
                detailItem.category ||
                '-'}
            </Descriptions.Item>
            <Descriptions.Item label="严重程度">
              <Tag color={SEVERITY_TAG_MAP[detailItem.severity || '']}>
                {SEVERITY_OPTIONS.find((o) => o.value === detailItem.severity)?.label || '-'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="症状">{detailItem.symptoms || '-'}</Descriptions.Item>
            <Descriptions.Item label="根本原因">{detailItem.root_cause || '-'}</Descriptions.Item>
            <Descriptions.Item label="解决方案">{detailItem.solution || '-'}</Descriptions.Item>
            <Descriptions.Item label="受影响系统">
              {detailItem.affected_system || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="有效性评分">
              {Math.round(detailItem.effectiveness_score * 100)}%
            </Descriptions.Item>
            <Descriptions.Item label="已验证">
              {detailItem.is_verified ? (
                <Tag color="green">已验证</Tag>
              ) : (
                <Tag>未验证</Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="标签">
              {detailItem.tags
                ? detailItem.tags
                    .split(',')
                    .map((t) => t.trim())
                    .filter(Boolean)
                    .map((t) => <Tag key={t}>{t}</Tag>)
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">
              {new Date(detailItem.created_at).toLocaleString('zh-CN')}
            </Descriptions.Item>
            <Descriptions.Item label="更新时间">
              {new Date(detailItem.updated_at).toLocaleString('zh-CN')}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default KnowledgeManagement;
