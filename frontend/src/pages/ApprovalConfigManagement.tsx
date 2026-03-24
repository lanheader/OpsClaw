// src/pages/ApprovalConfigManagement.tsx
/**
 * 审批配置管理界面
 * 用于配置哪些工具需要审批
 */

import { useState, useMemo } from 'react';
import {
  Table,
  Button,
  Space,
  Card,
  Tag,
  Typography,
  Switch,
  Input,
  Select,
  message,
  Alert
} from 'antd';
import {
  SyncOutlined,
  SearchOutlined,
  CheckOutlined,
  CloseOutlined,
  SafetyOutlined,
  RocketOutlined,
  WarningOutlined,
  CheckCircleOutlined
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  approvalConfigApi,
  type ToolApprovalConfig
} from '../api/approvalConfig';

const { Text } = Typography;
const { Search } = Input;

export const ApprovalConfigManagement: React.FC = () => {
  const queryClient = useQueryClient();

  // 状态管理
  const [searchText, setSearchText] = useState('');
  const [selectedGroup, setSelectedGroup] = useState<string | undefined>();
  const [selectedRiskLevel, setSelectedRiskLevel] = useState<string | undefined>();
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

  // 查询审批配置
  const { data: tools = [], isLoading } = useQuery({
    queryKey: ['approval-tools', selectedGroup, selectedRiskLevel],
    queryFn: () =>
      approvalConfigApi.getApprovalTools({
        group: selectedGroup,
        risk_level: selectedRiskLevel
      })
  });

  // 查询工具分组
  const { data: groups = [] } = useQuery({
    queryKey: ['approval-groups'],
    queryFn: approvalConfigApi.getApprovalGroups
  });

  // 同步工具
  const syncMutation = useMutation({
    mutationFn: approvalConfigApi.syncTools,
    onSuccess: (data) => {
      message.success(`同步成功：新增 ${data.synced_count} 个工具，总计 ${data.total_count} 个`);
      queryClient.invalidateQueries({ queryKey: ['approval-tools'] });
      queryClient.invalidateQueries({ queryKey: ['approval-groups'] });
    },
    onError: (error: any) => {
      message.error(`同步失败: ${error.response?.data?.detail || error.message}`);
    }
  });

  // 更新单个工具
  const updateMutation = useMutation({
    mutationFn: ({ toolName, requiresApproval }: { toolName: string; requiresApproval: boolean }) =>
      approvalConfigApi.updateToolApproval(toolName, requiresApproval),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approval-tools'] });
    },
    onError: (error: any) => {
      message.error(`更新失败: ${error.response?.data?.detail || error.message}`);
    }
  });

  // 批量更新
  const batchUpdateMutation = useMutation({
    mutationFn: ({ toolNames, requiresApproval }: { toolNames: string[]; requiresApproval: boolean }) =>
      approvalConfigApi.batchUpdateApproval({ tool_names: toolNames, requires_approval: requiresApproval }),
    onSuccess: (data) => {
      message.success(`批量更新成功：${data.updated_count} 个工具`);
      setSelectedRowKeys([]);
      queryClient.invalidateQueries({ queryKey: ['approval-tools'] });
    },
    onError: (error: any) => {
      message.error(`批量更新失败: ${error.response?.data?.detail || error.message}`);
    }
  });

  // 筛选数据
  const filteredTools = useMemo(() => {
    return tools.filter(tool => {
      if (searchText && !tool.tool_name.toLowerCase().includes(searchText.toLowerCase())) {
        return false;
      }
      return true;
    });
  }, [tools, searchText]);

  // 统计信息
  const stats = useMemo(() => {
    const total = tools.length;
    const enabled = tools.filter(t => t.requires_approval).length;
    const disabled = total - enabled;
    const highRisk = tools.filter(t => t.risk_level === 'high').length;
    const mediumRisk = tools.filter(t => t.risk_level === 'medium').length;
    const lowRisk = tools.filter(t => t.risk_level === 'low').length;

    return { total, enabled, disabled, highRisk, mediumRisk, lowRisk };
  }, [tools]);

  // 风险等级标签颜色
  const getRiskLevelColor = (level: string | null) => {
    switch (level) {
      case 'high': return 'error';
      case 'medium': return 'warning';
      case 'low': return 'success';
      default: return 'default';
    }
  };

  // 风险等级图标
  const getRiskLevelIcon = (level: string | null) => {
    switch (level) {
      case 'high': return <WarningOutlined />;
      case 'medium': return <RocketOutlined />;
      case 'low': return <SafetyOutlined />;
      default: return <SafetyOutlined />;
    }
  };

  // 表格列定义
  const columns = [
    {
      title: '工具名称',
      dataIndex: 'tool_name',
      key: 'tool_name',
      width: 200,
      render: (text: string) => (
        <Text code style={{ fontSize: 12 }}>{text}</Text>
      )
    },
    {
      title: '工具分组',
      dataIndex: 'tool_group',
      key: 'tool_group',
      width: 120,
      render: (text: string | null) => (
        <Tag color="blue">{text || 'default'}</Tag>
      )
    },
    {
      title: '风险等级',
      dataIndex: 'risk_level',
      key: 'risk_level',
      width: 100,
      render: (level: string | null) => (
        <Tag color={getRiskLevelColor(level)} icon={getRiskLevelIcon(level)}>
          {level?.toUpperCase() || 'UNKNOWN'}
        </Tag>
      )
    },
    {
      title: '需要审批',
      dataIndex: 'requires_approval',
      key: 'requires_approval',
      width: 100,
      render: (requiresApproval: boolean, record: ToolApprovalConfig) => (
        <Switch
          checked={requiresApproval}
          onChange={(checked) => {
            updateMutation.mutate({
              toolName: record.tool_name,
              requiresApproval: checked
            });
          }}
          loading={updateMutation.isPending}
          checkedChildren={<CheckOutlined />}
          unCheckedChildren={<CloseOutlined />}
        />
      )
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (text: string | null) => (
        <Text type="secondary">{text || '-'}</Text>
      )
    },
    {
      title: '最后更新',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 160,
      render: (date: string | null) => (
        <Text type="secondary">{date ? new Date(date).toLocaleString('zh-CN') : '-'}</Text>
      )
    }
  ];

  // 行选择配置
  const rowSelection = {
    selectedRowKeys,
    onChange: (newSelectedRowKeys: React.Key[]) => {
      setSelectedRowKeys(newSelectedRowKeys);
    }
  };

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* 统计信息卡片 */}
      <Card>
        <Space size="large" wrap>
          <Card size="small">
            <Space>
              <Text>总计:</Text>
              <Text strong>{stats.total}</Text>
            </Space>
          </Card>
          <Card size="small">
            <Space>
              <CheckCircleOutlined style={{ color: '#52c41a' }} />
              <Text>需要审批:</Text>
              <Text strong style={{ color: '#52c41a' }}>{stats.enabled}</Text>
            </Space>
          </Card>
          <Card size="small">
            <Space>
              <CloseOutlined style={{ color: '#8c8c8c' }} />
              <Text>免审批:</Text>
              <Text strong style={{ color: '#8c8c8c' }}>{stats.disabled}</Text>
            </Space>
          </Card>
          <Card size="small">
            <Space>
              <WarningOutlined style={{ color: '#ff4d4f' }} />
              <Text>高风险:</Text>
              <Text strong style={{ color: '#ff4d4f' }}>{stats.highRisk}</Text>
            </Space>
          </Card>
          <Card size="small">
            <Space>
              <RocketOutlined style={{ color: '#faad14' }} />
              <Text>中风险:</Text>
              <Text strong style={{ color: '#faad14' }}>{stats.mediumRisk}</Text>
            </Space>
          </Card>
          <Card size="small">
            <Space>
              <SafetyOutlined style={{ color: '#52c41a' }} />
              <Text>低风险:</Text>
              <Text strong style={{ color: '#52c41a' }}>{stats.lowRisk}</Text>
            </Space>
          </Card>
        </Space>
      </Card>

      {/* 操作栏 */}
      <Card title="审批配置管理">
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Text type="secondary">配置哪些工具需要用户批准才能执行</Text>

          <Space wrap>
            <Button
              type="primary"
              icon={<SyncOutlined />}
              onClick={() => syncMutation.mutate()}
              loading={syncMutation.isPending}
            >
              同步工具
            </Button>

            <Search
              placeholder="搜索工具名称"
              allowClear
              style={{ width: 200 }}
              onChange={e => setSearchText(e.target.value)}
              prefix={<SearchOutlined />}
            />

            <Select
              placeholder="工具分组"
              allowClear
              style={{ width: 150 }}
              value={selectedGroup}
              onChange={setSelectedGroup}
              options={groups.map(g => ({ label: g, value: g }))}
            />

            <Select
              placeholder="风险等级"
              allowClear
              style={{ width: 120 }}
              value={selectedRiskLevel}
              onChange={setSelectedRiskLevel}
              options={[
                { label: '高风险 (High)', value: 'high' },
                { label: '中风险 (Medium)', value: 'medium' },
                { label: '低风险 (Low)', value: 'low' }
              ]}
            />

            {selectedRowKeys.length > 0 && (
              <>
                <Button
                  onClick={() =>
                    batchUpdateMutation.mutate({
                      toolNames: selectedRowKeys as string[],
                      requiresApproval: true
                    })
                  }
                  loading={batchUpdateMutation.isPending}
                >
                  批量启用审批
                </Button>
                <Button
                  onClick={() =>
                    batchUpdateMutation.mutate({
                      toolNames: selectedRowKeys as string[],
                      requiresApproval: false
                    })
                  }
                  loading={batchUpdateMutation.isPending}
                >
                  批量禁用审批
                </Button>
              </>
            )}
          </Space>

          {/* 提示信息 */}
          {stats.enabled > 0 && (
            <Alert
              message="审批配置说明"
              description={`当前有 ${stats.enabled} 个工具配置为需要审批。这些工具在执行前会触发批准流程，用户需要确认后才会执行。`}
              type="info"
              showIcon
            />
          )}

          {/* 工具列表表格 */}
          <Table
            rowSelection={rowSelection}
            columns={columns}
            dataSource={filteredTools}
            loading={isLoading}
            rowKey="tool_name"
            pagination={{
              pageSize: 20,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 个工具`
            }}
            scroll={{ x: 1000 }}
          />
        </Space>
      </Card>
    </Space>
  );
};
