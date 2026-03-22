// src/pages/RoleManagement.tsx
import { useState } from 'react';
import {
  Table,
  Button,
  Space,
  Modal,
  Form,
  Input,
  message,
  Popconfirm,
  Tag,
  Checkbox,
  Divider,
  Alert,
  Card
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  SafetyOutlined,
  LockOutlined
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  rolesApi,
  type RoleCreateRequest,
  type RoleUpdateRequest,
  type Role
} from '../api/roles';
import { usePermission } from '../contexts/PermissionContext';

const { TextArea } = Input;

export const RoleManagement: React.FC = () => {
  const { hasPermission } = usePermission();
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isPermissionModalOpen, setIsPermissionModalOpen] = useState(false);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([]);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const queryClient = useQueryClient();

  // Fetch roles - 先调用所有 Hooks
  const { data: roles, isLoading } = useQuery({
    queryKey: ['roles'],
    queryFn: rolesApi.getRoles
  });

  // Fetch all permissions
  const { data: allPermissions } = useQuery({
    queryKey: ['permissions'],
    queryFn: rolesApi.getAllPermissions
  });

  // Create role mutation
  const createMutation = useMutation({
    mutationFn: rolesApi.createRole,
    onSuccess: () => {
      message.success('角色创建成功');
      queryClient.invalidateQueries({ queryKey: ['roles'] });
      setIsCreateModalOpen(false);
      createForm.resetFields();
    },
    onError: (error: any) => {
      message.error(`创建失败: ${error.response?.data?.detail || error.message}`);
    }
  });

  // Update role mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: RoleUpdateRequest }) =>
      rolesApi.updateRole(id, data),
    onSuccess: () => {
      message.success('角色更新成功');
      queryClient.invalidateQueries({ queryKey: ['roles'] });
      setIsEditModalOpen(false);
      editForm.resetFields();
      setSelectedRole(null);
    },
    onError: (error: any) => {
      message.error(`更新失败: ${error.response?.data?.detail || error.message}`);
    }
  });

  // Delete role mutation
  const deleteMutation = useMutation({
    mutationFn: rolesApi.deleteRole,
    onSuccess: () => {
      message.success('角色删除成功');
      queryClient.invalidateQueries({ queryKey: ['roles'] });
    },
    onError: (error: any) => {
      message.error(`删除失败: ${error.response?.data?.detail || error.message}`);
    }
  });

  // Update permissions mutation
  const updatePermissionsMutation = useMutation({
    mutationFn: ({ id, permission_codes }: { id: number; permission_codes: string[] }) =>
      rolesApi.updateRolePermissions(id, { permission_codes }),
    onSuccess: () => {
      message.success('权限配置成功');
      queryClient.invalidateQueries({ queryKey: ['roles'] });
      setIsPermissionModalOpen(false);
      setSelectedRole(null);
      setSelectedPermissions([]);
    },
    onError: (error: any) => {
      message.error(`配置失败: ${error.response?.data?.detail || error.message}`);
    }
  });

  // Check permission - 在所有 Hooks 调用之后再做权限检查
  if (!hasPermission('manage_roles')) {
    return (
      <Alert
        message="权限不足"
        description="您没有权限访问角色管理页面"
        type="error"
        showIcon
      />
    );
  }

  // Handlers
  const handleCreate = () => {
    createForm.validateFields().then((values: RoleCreateRequest) => {
      createMutation.mutate(values);
    });
  };

  const handleEdit = (role: Role) => {
    if (role.is_system) {
      message.warning('系统角色不可编辑');
      return;
    }
    setSelectedRole(role);
    editForm.setFieldsValue({
      name: role.name,
      description: role.description
    });
    setIsEditModalOpen(true);
  };

  const handleUpdate = () => {
    if (!selectedRole) return;
    editForm.validateFields().then((values: RoleUpdateRequest) => {
      updateMutation.mutate({ id: selectedRole.id, data: values });
    });
  };

  const handleDelete = (role: Role) => {
    if (role.is_system) {
      message.warning('系统角色不可删除');
      return;
    }
    deleteMutation.mutate(role.id);
  };

  const handleConfigurePermissions = async (role: Role) => {
    setSelectedRole(role);
    try {
      const permissions = await rolesApi.getRolePermissions(role.id);
      setSelectedPermissions(permissions.map(p => p.code));
      setIsPermissionModalOpen(true);
    } catch (error: any) {
      message.error(`获取权限失败: ${error.response?.data?.detail || error.message}`);
    }
  };

  const handleUpdatePermissions = () => {
    if (!selectedRole) return;
    updatePermissionsMutation.mutate({
      id: selectedRole.id,
      permission_codes: selectedPermissions
    });
  };

  // Group permissions by category - allPermissions is already grouped
  const groupedPermissions = allPermissions || {
    menu: [],
    tool: [],
    api: []
  };

  const categoryLabels = {
    menu: '菜单权限',
    tool: '工具权限',
    api: 'API权限'
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80
    },
    {
      title: '角色名称',
      dataIndex: 'name',
      key: 'name'
    },
    {
      title: '角色代码',
      dataIndex: 'code',
      key: 'code'
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      render: (text: string | null) => text || '-'
    },
    {
      title: '类型',
      dataIndex: 'is_system',
      key: 'is_system',
      render: (isSystem: boolean) =>
        isSystem ? (
          <Tag icon={<LockOutlined />} color="blue">
            系统角色
          </Tag>
        ) : (
          <Tag>自定义角色</Tag>
        )
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (text: string) => new Date(text).toLocaleString('zh-CN')
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: Role) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
            disabled={record.is_system}
          >
            编辑
          </Button>
          <Button
            type="link"
            size="small"
            icon={<SafetyOutlined />}
            onClick={() => handleConfigurePermissions(record)}
          >
            配置权限
          </Button>
          <Popconfirm
            title="确定要删除这个角色吗？"
            description="删除后无法恢复，请确认该角色未分配给任何用户"
            onConfirm={() => handleDelete(record)}
            okText="确定"
            cancelText="取消"
            disabled={record.is_system}
          >
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
              disabled={record.is_system}
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card
        title="角色管理"
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setIsCreateModalOpen(true)}
          >
            创建角色
          </Button>
        }
      >
        <Table
          columns={columns}
          dataSource={roles}
        rowKey="id"
        loading={isLoading}
        scroll={{ x: 'max-content' }}
        pagination={{ pageSize: 10 }}
      />
      </Card>

      {/* Create Role Modal */}
      <Modal
        title="创建角色"
        open={isCreateModalOpen}
        onOk={handleCreate}
        onCancel={() => {
          setIsCreateModalOpen(false);
          createForm.resetFields();
        }}
        confirmLoading={createMutation.isPending}
      >
        <Form form={createForm} layout="vertical">
          <Form.Item
            name="name"
            label="角色名称"
            rules={[{ required: true, message: '请输入角色名称' }]}
          >
            <Input placeholder="请输入角色名称" />
          </Form.Item>
          <Form.Item
            name="code"
            label="角色代码"
            rules={[
              { required: true, message: '请输入角色代码' },
              { pattern: /^[a-z_]+$/, message: '只能包含小写字母和下划线' }
            ]}
          >
            <Input placeholder="例如: operator, viewer" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={3} placeholder="请输入角色描述（可选）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit Role Modal */}
      <Modal
        title="编辑角色"
        open={isEditModalOpen}
        onOk={handleUpdate}
        onCancel={() => {
          setIsEditModalOpen(false);
          editForm.resetFields();
          setSelectedRole(null);
        }}
        confirmLoading={updateMutation.isPending}
      >
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="name"
            label="角色名称"
            rules={[{ required: true, message: '请输入角色名称' }]}
          >
            <Input placeholder="请输入角色名称" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={3} placeholder="请输入角色描述（可选）" />
          </Form.Item>
          <Alert
            message="提示"
            description="角色代码创建后不可修改"
            type="info"
            showIcon
            style={{ marginTop: 8 }}
          />
        </Form>
      </Modal>

      {/* Permission Configuration Modal */}
      <Modal
        title={`配置权限 - ${selectedRole?.name}`}
        open={isPermissionModalOpen}
        onOk={handleUpdatePermissions}
        onCancel={() => {
          setIsPermissionModalOpen(false);
          setSelectedRole(null);
          setSelectedPermissions([]);
        }}
        confirmLoading={updatePermissionsMutation.isPending}
        width={700}
      >
        <div style={{ maxHeight: 'calc(80vh - 200px)', overflowY: 'auto' }}>
          {Object.entries(groupedPermissions).map(([category, permissions]) => (
            <div key={category} style={{ marginBottom: 24 }}>
              <Divider orientation="left">
                {categoryLabels[category as keyof typeof categoryLabels]}
              </Divider>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {permissions.map((perm) => (
                  <Checkbox
                    key={perm.code}
                    checked={selectedPermissions.includes(perm.code)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedPermissions([...selectedPermissions, perm.code]);
                      } else {
                        setSelectedPermissions(selectedPermissions.filter(p => p !== perm.code));
                      }
                    }}
                  >
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <span style={{ fontWeight: 500 }}>{perm.name}</span>
                      {perm.description && (
                        <span style={{ fontSize: 12, color: '#999' }}>
                          {perm.description}
                        </span>
                      )}
                    </div>
                  </Checkbox>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Modal>
    </Space>
  );
};
