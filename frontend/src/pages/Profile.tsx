// src/pages/Profile.tsx
/**
 * 个人信息页面 - 包含头像上传
 */
import React, { useState } from 'react';
import {
  Card,
  Form,
  Input,
  Button,
  message,
  Spin,
  Typography,
  Avatar,
  Upload,
  Space,
  Divider
} from 'antd';
import {
  UserOutlined,
  CameraOutlined,
  SaveOutlined,
  MailOutlined,
  IdcardOutlined
} from '@ant-design/icons';
import type { UploadChangeParam } from 'antd/es/upload';
import type { UploadFile, UploadProps } from 'antd/es/upload/interface';
import { useAuth } from '@/contexts/AuthContext';
import { authApi } from '@/api/auth';

const { Text } = Typography;

const Profile: React.FC = () => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [form] = Form.useForm();

  // 加载用户信息
  const loadUserProfile = async () => {
    setLoading(true);
    try {
      const currentUser = await authApi.getCurrentUser();
      form.setFieldsValue({
        username: currentUser.username,
        email: currentUser.email,
        full_name: currentUser.full_name || ''
      });

      // 如果用户有头像，设置头像 URL
      if ((currentUser as any).avatar_url) {
        setAvatarUrl((currentUser as any).avatar_url);
      }
    } catch (error) {
      message.error('加载用户信息失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    loadUserProfile();
  }, []);

  // 头像上传处理
  const handleAvatarChange: UploadProps['onChange'] = (info: UploadChangeParam<UploadFile>) => {
    if (info.file.status === 'uploading') {
      setLoading(true);
      return;
    }
    if (info.file.status === 'done') {
      // 上传成功，获取新的头像 URL
      const response = info.file.response;
      if (response && response.avatar_url) {
        setAvatarUrl(response.avatar_url);
        message.success('头像上传成功');

        // 重新加载用户信息
        loadUserProfile();
      }
      setLoading(false);
    } else if (info.file.status === 'error') {
      message.error('头像上传失败');
      setLoading(false);
    }
  };

  // 上传前的验证
  const beforeUpload = (file: File) => {
    const isJpgOrPng = file.type === 'image/jpeg' || file.type === 'image/png';
    if (!isJpgOrPng) {
      message.error('只能上传 JPG/PNG 格式的图片');
      return false;
    }
    const isLt2M = file.size / 1024 / 1024 < 2;
    if (!isLt2M) {
      message.error('图片大小不能超过 2MB');
      return false;
    }
    return true;
  };

  // 保存个人信息
  const handleSave = async () => {
    setSaving(true);
    try {
      // TODO: 调用更新用户信息的 API
      // await authApi.updateProfile(values);
      message.success('个人信息保存成功');
    } catch (error) {
      message.error('保存失败');
      console.error(error);
    } finally {
      setSaving(false);
    }
  };

  if (loading && !user) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* 个人信息卡片 */}
        <Card
          title="个人信息"
          extra={
            <Space>
              <Button onClick={() => form.resetFields()}>
                重置
              </Button>
              <Button
                type="primary"
                onClick={() => form.submit()}
                icon={<SaveOutlined />}
                loading={saving}
              >
                保存更改
              </Button>
            </Space>
          }
        >
          <Text type="secondary">查看和更新您的个人资料</Text>

          <Divider style={{ marginTop: 24 }} />

          <Form
            form={form}
            layout="vertical"
            onFinish={handleSave}
          >
            {/* 头像上传区域 */}
            <div style={{ textAlign: 'center', marginBottom: 32 }}>
              <div style={{ display: 'inline-block', position: 'relative' }}>
                <Avatar
                  size={100}
                  src={avatarUrl}
                  icon={<UserOutlined />}
                  style={{ marginBottom: 16 }}
                />
                <Upload
                  name="avatar"
                  action="/api/v1/users/avatar"
                  headers={{
                    Authorization: `Bearer ${localStorage.getItem('token') || ''}`
                  }}
                  showUploadList={false}
                  beforeUpload={beforeUpload}
                  onChange={handleAvatarChange}
                  accept="image/png,image/jpeg"
                >
                  <Button
                    type="primary"
                    shape="circle"
                    icon={<CameraOutlined />}
                    size="small"
                    style={{
                      position: 'absolute',
                      bottom: 16,
                      right: 0
                    }}
                  />
                </Upload>
              </div>
              <div style={{ marginTop: 12 }}>
                <Text type="secondary">支持 JPG、PNG 格式，文件大小不超过 2MB</Text>
              </div>
            </div>

            <Form.Item
              label="用户名"
              name="username"
            >
              <Input
                prefix={<IdcardOutlined />}
                placeholder="用户名"
                disabled
              />
            </Form.Item>

            <Form.Item
              label="邮箱"
              name="email"
            >
              <Input
                prefix={<MailOutlined />}
                placeholder="邮箱"
                disabled
              />
            </Form.Item>

            <Form.Item
              label="姓名"
              name="full_name"
              rules={[{ max: 100, message: '姓名不能超过100个字符' }]}
            >
              <Input
                placeholder="请输入您的姓名"
              />
            </Form.Item>
          </Form>
        </Card>

        {/* 账户信息卡片 */}
        <Card title="账户信息">
          <Space direction="vertical" style={{ width: '100%' }}>
            <div>
              <Text type="secondary">账户状态：</Text>
              <Text style={{ marginLeft: 8 }}>
                {user?.is_active ? (
                  <span style={{ color: '#52c41a' }}>● 活跃</span>
                ) : (
                  <span style={{ color: '#ff4d4f' }}>● 未激活</span>
                )}
              </Text>
            </div>
            <div>
              <Text type="secondary">账户类型：</Text>
              <Text style={{ marginLeft: 8 }}>
                {user?.is_superuser ? '管理员' : '普通用户'}
              </Text>
            </div>
            <div>
              <Text type="secondary">注册时间：</Text>
              <Text style={{ marginLeft: 8 }}>
                {user?.created_at ? new Date(user.created_at).toLocaleString('zh-CN') : '-'}
              </Text>
            </div>
            <div>
              <Text type="secondary">最后登录：</Text>
              <Text style={{ marginLeft: 8 }}>
                {user?.last_login_at ? new Date(user.last_login_at).toLocaleString('zh-CN') : '-'}
              </Text>
            </div>
          </Space>
        </Card>
      </Space>
    </div>
  );
};

export default Profile;
