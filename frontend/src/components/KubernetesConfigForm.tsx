// src/components/KubernetesConfigForm.tsx
/**
 * Kubernetes 配置表单组件
 */

import React, { useState, useEffect } from 'react';
import {
  Form,
  Input,
  Switch,
  Button,
  Space,
  message,
  Typography,
  Divider,
  Radio,
  Alert,
  Spin,
  Tag,
} from 'antd';
import {
  SaveOutlined,
  ApiOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  kubernetesApi,
  KubernetesConfigUpdate,
  AuthMode,
} from '../api/kubernetes';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const KubernetesConfigForm: React.FC = () => {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const [authMode, setAuthMode] = useState<AuthMode>('kubeconfig');
  const [testResult, setTestResult] = useState<{
    loading: boolean;
    success?: boolean;
    message?: string;
    details?: string;
  } | null>(null);

  // 加载配置
  const { data: config, isLoading } = useQuery({
    queryKey: ['kubernetes-config'],
    queryFn: kubernetesApi.getConfig,
  });

  // 更新配置
  const updateMutation = useMutation({
    mutationFn: (data: KubernetesConfigUpdate) => kubernetesApi.updateConfig(data),
    onSuccess: () => {
      message.success('Kubernetes 配置保存成功');
      queryClient.invalidateQueries({ queryKey: ['kubernetes-config'] });
    },
    onError: (error: any) => {
      message.error(`保存失败: ${error.response?.data?.detail || error.message}`);
    },
  });

  // 当配置加载后，填充表单
  useEffect(() => {
    if (config) {
      form.setFieldsValue({
        enabled: config.enabled,
        auth_mode: config.auth_mode,
        // token 模式字段
        api_host: config.api_host,
        // kubeconfig 模式字段不需要填充（因为是脱敏的）
      });
      setAuthMode(config.auth_mode);
    }
  }, [config, form]);

  // 保存配置
  const handleSave = async () => {
    try {
      const values = await form.validateFields();

      const updateData: KubernetesConfigUpdate = {
        enabled: values.enabled,
        auth_mode: values.auth_mode,
      };

      // 根据认证模式添加对应的配置
      if (values.auth_mode === 'kubeconfig') {
        if (values.kubeconfig_content) {
          updateData.kubeconfig_content = values.kubeconfig_content;
        }
      } else {
        if (values.api_host) {
          updateData.api_host = values.api_host;
        }
        if (values.token) {
          updateData.token = values.token;
        }
        if (values.ca_cert) {
          updateData.ca_cert = values.ca_cert;
        }
      }

      updateMutation.mutate(updateData);
    } catch (error) {
      // 表单验证错误
    }
  };

  // 测试连接
  const handleTest = async () => {
    setTestResult({ loading: true });

    try {
      const values = form.getFieldsValue();

      const testRequest: any = {
        auth_mode: values.auth_mode,
      };

      if (values.auth_mode === 'kubeconfig') {
        if (values.kubeconfig_content) {
          testRequest.kubeconfig_content = values.kubeconfig_content;
        }
      } else {
        if (values.api_host) testRequest.api_host = values.api_host;
        if (values.token) testRequest.token = values.token;
        if (values.ca_cert) testRequest.ca_cert = values.ca_cert;
      }

      const result = await kubernetesApi.testConnection(
        Object.values(testRequest).some(v => v) ? testRequest : undefined
      );

      setTestResult({
        loading: false,
        success: result.success,
        message: result.message,
        details: result.cluster_info
          ? `${result.cluster_info} | Version: ${result.server_version} | Response: ${result.response_time_ms}ms`
          : undefined,
      });

      if (result.success) {
        message.success('连接测试成功');
      } else {
        message.error(`连接测试失败: ${result.message}`);
      }
    } catch (error: any) {
      setTestResult({
        loading: false,
        success: false,
        message: error.response?.data?.detail || error.message,
      });
      message.error(`连接测试失败: ${error.message}`);
    }
  };

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '40px 0' }}>
        <Spin indicator={<LoadingOutlined spin />} tip="加载配置中..." />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 800 }}>
      <Alert
        message="Kubernetes 连接配置"
        description={
          <div>
            <p>支持两种认证方式：</p>
            <ul style={{ marginBottom: 0 }}>
              <li><strong>kubeconfig</strong>：粘贴 kubeconfig 文件内容（推荐本地开发环境）</li>
              <li><strong>token</strong>：使用 ServiceAccount Token 连接（推荐生产环境）</li>
            </ul>
          </div>
        }
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
      />

      <Form
        form={form}
        layout="vertical"
        component={false}
        initialValues={{
          enabled: false,
          auth_mode: 'kubeconfig',
        }}
      >
        <Form.Item
          name="enabled"
          label="启用 Kubernetes 集成"
          valuePropName="checked"
        >
          <Switch checkedChildren="启用" unCheckedChildren="禁用" />
        </Form.Item>

        <Divider orientation="left">认证配置</Divider>

        <Form.Item
          name="auth_mode"
          label="认证模式"
          tooltip="选择连接 Kubernetes 的方式"
        >
          <Radio.Group onChange={(e) => setAuthMode(e.target.value)}>
            <Radio.Button value="kubeconfig">kubeconfig 文件</Radio.Button>
            <Radio.Button value="token">ServiceAccount Token</Radio.Button>
          </Radio.Group>
        </Form.Item>

        {authMode === 'kubeconfig' ? (
          <>
            <Form.Item
              name="kubeconfig_content"
              label="kubeconfig 内容"
              tooltip="粘贴完整的 kubeconfig 文件内容（YAML 格式）"
              rules={[{ required: true, message: '请输入 kubeconfig 内容' }]}
            >
              <TextArea
                rows={12}
                style={{ fontFamily: 'monospace', fontSize: '12px' }}
                placeholder={`apiVersion: v1
kind: Config
clusters:
- cluster:
    certificate-authority-data: ...
    server: https://k8s-api.example.com:6443
  name: my-cluster
contexts:
...`}
              />
            </Form.Item>
            {config?.kubeconfig_content_masked && (
              <Text type="secondary">
                当前配置预览: {config.kubeconfig_content_masked}
              </Text>
            )}
          </>
        ) : (
          <>
            <Form.Item
              name="api_host"
              label="API Server 地址"
              tooltip="Kubernetes API Server 地址"
              rules={[{ required: true, message: '请输入 API Server 地址' }]}
            >
              <Input placeholder="https://k8s-api.example.com:6443" />
            </Form.Item>

            <Form.Item
              name="token"
              label="ServiceAccount Token"
              tooltip="具有适当权限的 ServiceAccount Token"
              rules={[{ required: true, message: '请输入 Token' }]}
            >
              <Input.Password
                placeholder="eyJhbGciOiJSUzI1NiIsImtpZCI6..."
                style={{ fontFamily: 'monospace' }}
              />
            </Form.Item>

            <Form.Item
              name="ca_cert"
              label="CA 证书（可选）"
              tooltip="自定义 CA 证书内容（PEM 格式），留空则使用系统默认证书"
            >
              <TextArea
                rows={6}
                style={{ fontFamily: 'monospace', fontSize: '12px' }}
                placeholder={`-----BEGIN CERTIFICATE-----
MIID...
-----END CERTIFICATE-----`}
              />
            </Form.Item>

            {config?.token_masked && (
              <Text type="secondary">
                当前 Token 预览: {config.token_masked}
              </Text>
            )}
          </>
        )}

        <Divider />

        <Form.Item>
          <Space>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              onClick={handleSave}
              loading={updateMutation.isPending}
            >
              保存配置
            </Button>
            <Button
              icon={<ApiOutlined />}
              onClick={handleTest}
              loading={testResult?.loading}
            >
              测试连接
            </Button>
          </Space>
        </Form.Item>
      </Form>

      {/* 测试结果 */}
      {testResult && !testResult.loading && (
        <div style={{ marginTop: 16 }}>
          {testResult.success ? (
            <Alert
              message="连接成功"
              description={
                <div>
                  <Paragraph style={{ marginBottom: 0 }}>{testResult.message}</Paragraph>
                  {testResult.details && (
                    <Text type="secondary">{testResult.details}</Text>
                  )}
                </div>
              }
              type="success"
              showIcon
              icon={<CheckCircleOutlined />}
            />
          ) : (
            <Alert
              message="连接失败"
              description={testResult.message}
              type="error"
              showIcon
              icon={<CloseCircleOutlined />}
            />
          )}
        </div>
      )}

      {/* 当前状态 */}
      {config && (
        <div style={{ marginTop: 24 }}>
          <Divider orientation="left">当前状态</Divider>
          <Space>
            <Text>集成状态:</Text>
            <Tag color={config.enabled ? 'success' : 'default'}>
              {config.enabled ? '已启用' : '未启用'}
            </Tag>
            <Text>认证模式:</Text>
            <Tag color="blue">{config.auth_mode}</Tag>
          </Space>
        </div>
      )}
    </div>
  );
};

export default KubernetesConfigForm;
