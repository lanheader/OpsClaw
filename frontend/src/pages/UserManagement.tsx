// src/pages/UserManagement.tsx
import { useState, useEffect } from 'react';
import {
  Table,
  Button,
  Space,
  Modal,
  Form,
  Input,
  Switch,
  message,
  Popconfirm,
  Tag,
  Typography,
  Checkbox,
  Spin,
  Card
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  KeyOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  TeamOutlined
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { usersApi, type UserCreateRequest, type UserUpdateRequest, type UserRole } from '../api/users';
import { rolesApi, type Role } from '../api/roles';
import type { User } from '../api/auth';

export const UserManagement: React.FC = () => {
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isResetPasswordModalOpen, setIsResetPasswordModalOpen] = useState(false);
  const [isAssignRolesModalOpen, setIsAssignRolesModalOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [selectedRoleIds, setSelectedRoleIds] = useState<number[]>([]);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [resetPasswordForm] = Form.useForm();
  const queryClient = useQueryClient();

  // Fetch users
  const { data: users, isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: usersApi.getUsers
  });

  // Fetch all roles
  const { data: allRoles } = useQuery({
    queryKey: ['roles'],
    queryFn: rolesApi.getRoles
  });

  // Fetch user roles when modal opens
  const { data: userRoles, isLoading: isLoadingUserRoles } = useQuery({
    queryKey: ['userRoles', selectedUser?.id],
    queryFn: () => selectedUser ? usersApi.getUserRoles(selectedUser.id) : Promise.resolve([]),
    enabled: isAssignRolesModalOpen && !!selectedUser
  });

  // Create user mutation
  const createMutation = useMutation({
    mutationFn: usersApi.createUser,
    onSuccess: () => {
      message.success('用户创建成功');
      queryClient.invalidateQueries({ queryKey: ['users'] });
      setIsCreateModalOpen(false);
      createForm.resetFields();
    },
    onError: (error: any) => {
      message.error(`创建失败: ${error.response?.data?.detail || error.message}`);
    }
  });

  // Update user mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: UserUpdateRequest }) =>
      usersApi.updateUser(id, data),
    onSuccess: () => {
      message.success('用户更新成功');
      queryClient.invalidateQueries({ queryKey: ['users'] });
      setIsEditModalOpen(false);
      editForm.resetFields();
      setSelectedUser(null);
    },
    onError: (error: any) => {
      message.error(`更新失败: ${error.response?.data?.detail || error.message}`);
    }
  });

  // Delete user mutation
  const deleteMutation = useMutation({
    mutationFn: usersApi.deleteUser,
    onSuccess: () => {
      message.success('用户删除成功');
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: (error: any) => {
      message.error(`删除失败: ${error.response?.data?.detail || error.message}`);
    }
  });

  // Reset password mutation
  const resetPasswordMutation = useMutation({
    mutationFn: ({ id, new_password }: { id: number; new_password: string }) =>
      usersApi.resetPassword(id, { new_password }),
    onSuccess: () => {
      message.success('密码重置成功');
      setIsResetPasswordModalOpen(false);
      resetPasswordForm.resetFields();
      setSelectedUser(null);
    },
    onError: (error: any) => {
      message.error(`重置失败: ${error.response?.data?.detail || error.message}`);
    }
  });

  // Assign roles mutation
  const assignRolesMutation = useMutation({
    mutationFn: ({ id, role_ids }: { id: number; role_ids: number[] }) =>
      usersApi.assignRoles(id, { role_ids }),
    onSuccess: () => {
      message.success('角色分配成功');
      queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.invalidateQueries({ queryKey: ['userRoles'] });
      setIsAssignRolesModalOpen(false);
      setSelectedUser(null);
      setSelectedRoleIds([]);
    },
    onError: (error: any) => {
      message.error(`分配失败: ${error.response?.data?.detail || error.message}`);
    }
  });

  // Handlers
  const handleCreate = () => {
    createForm.validateFields().then((values: UserCreateRequest) => {
      createMutation.mutate(values);
    });
  };

  const handleEdit = (user: User) => {
    setSelectedUser(user);
    editForm.setFieldsValue({
      email: user.email,
      full_name: user.full_name,
      feishu_user_id: user.feishu_user_id,
      is_active: user.is_active,
      is_superuser: user.is_superuser
    });
    setIsEditModalOpen(true);
  };

  const handleUpdate = () => {
    if (!selectedUser) return;
    editForm.validateFields().then((values: UserUpdateRequest) => {
      updateMutation.mutate({ id: selectedUser.id, data: values });
    });
  };

  const handleDelete = (id: number) => {
    deleteMutation.mutate(id);
  };

  const handleResetPassword = (user: User) => {
    setSelectedUser(user);
    setIsResetPasswordModalOpen(true);
  };

  const handleResetPasswordSubmit = () => {
    if (!selectedUser) return;
    resetPasswordForm.validateFields().then((values) => {
      resetPasswordMutation.mutate({
        id: selectedUser.id,
        new_password: values.new_password
      });
    });
  };

  const handleAssignRoles = (user: User) => {
    setSelectedUser(user);
    setIsAssignRolesModalOpen(true);
  };

  const handleAssignRolesSubmit = () => {
    if (!selectedUser) return;
    assignRolesMutation.mutate({
      id: selectedUser.id,
      role_ids: selectedRoleIds
    });
  };

  // Update selected role IDs when user roles are loaded
  useEffect(() => {
    if (userRoles) {
      setSelectedRoleIds(userRoles.map(role => role.id));
    }
  }, [userRoles]);

  const handleRoleCheckboxChange = (roleId: number, checked: boolean) => {
    if (checked) {
      setSelectedRoleIds([...selectedRoleIds, roleId]);
    } else {
      setSelectedRoleIds(selectedRoleIds.filter(id => id !== roleId));
    }
  };

  // Helper function to get user roles for display
  const getUserRolesForDisplay = (_userId: number): UserRole[] => {
    // In a real implementation, this would fetch from the backend
    // For now, we'll return an empty array as a placeholder
    return [];
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80
    },
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username'
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email'
    },
    {
      title: '姓名',
      dataIndex: 'full_name',
      key: 'full_name',
      render: (text: string | null) => text || '-'
    },
    {
      title: '飞书ID',
      dataIndex: 'feishu_user_id',
      key: 'feishu_user_id',
      render: (text: string | null) => text || '-'
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (isActive: boolean) =>
        isActive ? (
          <Tag icon={<CheckCircleOutlined />} color="success">
            激活
          </Tag>
        ) : (
          <Tag icon={<CloseCircleOutlined />} color="error">
            禁用
          </Tag>
        )
    },
    {
      title: '管理员',
      dataIndex: 'is_superuser',
      key: 'is_superuser',
      render: (isSuperuser: boolean) =>
        isSuperuser ? (
          <Tag color="red">是</Tag>
        ) : (
          <Tag>否</Tag>
        )
    },
    {
      title: '角色',
      key: 'roles',
      render: (_: any, record: User) => {
        const roles = getUserRolesForDisplay(record.id);
        if (roles.length === 0) {
          return <Tag color="default">无角色</Tag>;
        }
        return (
          <>
            {roles.map(role => (
              <Tag key={role.id} color="blue">
                {role.name}
              </Tag>
            ))}
          </>
        );
      }
    },
    {
      title: '最后登录',
      dataIndex: 'last_login_at',
      key: 'last_login_at',
      render: (text: string | null) =>
        text ? new Date(text).toLocaleString('zh-CN') : '从未登录'
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: User) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Button
            type="link"
            size="small"
            icon={<TeamOutlined />}
            onClick={() => handleAssignRoles(record)}
          >
            分配角色
          </Button>
          <Button
            type="link"
            size="small"
            icon={<KeyOutlined />}
            onClick={() => handleResetPassword(record)}
          >
            重置密码
          </Button>
          <Popconfirm
            title="确定要删除这个用户吗？"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
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
        title="用户管理"
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setIsCreateModalOpen(true)}
          >
            创建用户
          </Button>
        }
      >
        <Table
          columns={columns}
          dataSource={users}
          rowKey="id"
          loading={isLoading}
          scroll={{ x: 'max-content' }}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      {/* Create User Modal */}
      <Modal
        title="创建用户"
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
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input placeholder="请输入用户名" />
          </Form.Item>
          <Form.Item
            name="email"
            label="邮箱"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '请输入有效的邮箱地址' }
            ]}
          >
            <Input placeholder="请输入邮箱" />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 6, message: '密码至少6个字符' }
            ]}
          >
            <Input.Password placeholder="请输入密码" />
          </Form.Item>
          <Form.Item name="full_name" label="姓名">
            <Input placeholder="请输入姓名（可选）" />
          </Form.Item>
          <Form.Item name="is_active" label="激活状态" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
          <Form.Item name="is_superuser" label="管理员权限" valuePropName="checked" initialValue={false}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit User Modal */}
      <Modal
        title="编辑用户"
        open={isEditModalOpen}
        onOk={handleUpdate}
        onCancel={() => {
          setIsEditModalOpen(false);
          editForm.resetFields();
          setSelectedUser(null);
        }}
        confirmLoading={updateMutation.isPending}
      >
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="email"
            label="邮箱"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '请输入有效的邮箱地址' }
            ]}
          >
            <Input placeholder="请输入邮箱" />
          </Form.Item>
          <Form.Item name="full_name" label="姓名">
            <Input placeholder="请输入姓名（可选）" />
          </Form.Item>
          <Form.Item name="feishu_user_id" label="飞书用户ID">
            <Input placeholder="请输入飞书用户ID（可选）" />
          </Form.Item>
          <Form.Item name="is_active" label="激活状态" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="is_superuser" label="管理员权限" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* Reset Password Modal */}
      <Modal
        title="重置密码"
        open={isResetPasswordModalOpen}
        onOk={handleResetPasswordSubmit}
        onCancel={() => {
          setIsResetPasswordModalOpen(false);
          resetPasswordForm.resetFields();
          setSelectedUser(null);
        }}
        confirmLoading={resetPasswordMutation.isPending}
      >
        <Form form={resetPasswordForm} layout="vertical">
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 6, message: '密码至少6个字符' }
            ]}
          >
            <Input.Password placeholder="请输入新密码" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Assign Roles Modal */}
      <Modal
        title={`分配角色 - ${selectedUser?.username || ''}`}
        open={isAssignRolesModalOpen}
        onOk={handleAssignRolesSubmit}
        onCancel={() => {
          setIsAssignRolesModalOpen(false);
          setSelectedUser(null);
          setSelectedRoleIds([]);
        }}
        confirmLoading={assignRolesMutation.isPending}
        width={600}
      >
        <Spin spinning={isLoadingUserRoles}>
          <div style={{ marginBottom: 16 }}>
            <Typography.Text type="secondary">
              选择要分配给该用户的角色（可多选）
            </Typography.Text>
          </div>
          {allRoles && allRoles.length > 0 ? (
            <div style={{ maxHeight: 'calc(70vh - 150px)', overflowY: 'auto' }}>
              {allRoles.map((role: Role) => (
                <div
                  key={role.id}
                  style={{
                    padding: '12px',
                    border: '1px solid #f0f0f0',
                    borderRadius: '4px',
                    marginBottom: '8px',
                    backgroundColor: selectedRoleIds.includes(role.id) ? '#e6f7ff' : '#fff'
                  }}
                >
                  <Checkbox
                    checked={selectedRoleIds.includes(role.id)}
                    onChange={(e) => handleRoleCheckboxChange(role.id, e.target.checked)}
                  >
                    <Space direction="vertical" size={0}>
                      <Space>
                        <Typography.Text strong>{role.name}</Typography.Text>
                        <Tag color="blue">{role.code}</Tag>
                        {role.is_system && <Tag color="orange">系统角色</Tag>}
                      </Space>
                      {role.description && (
                        <Typography.Text type="secondary" style={{ fontSize: '12px' }}>
                          {role.description}
                        </Typography.Text>
                      )}
                    </Space>
                  </Checkbox>
                </div>
              ))}
            </div>
          ) : (
            <Typography.Text type="secondary">暂无可用角色</Typography.Text>
          )}
        </Spin>
      </Modal>
    </Space>
  );
};
