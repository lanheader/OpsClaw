import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card,
  Steps,
  Form,
  Input,
  Button,
  Switch,
  Select,
  message,
  Typography,
  Space,
  Result,
} from 'antd';
import {
  UserOutlined,
  CloudServerOutlined,
  DashboardOutlined,
  FileSearchOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import { onboardingApi } from '../api/onboarding';

const { Title, Text } = Typography;
const { TextArea } = Input;

const OnboardingWizard: React.FC = () => {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [completed, setCompleted] = useState(false);

  const [step1Form] = Form.useForm();
  const [step2Form] = Form.useForm();
  const [step3Form] = Form.useForm();
  const [step4Form] = Form.useForm();

  // K8s 配置状态
  const [k8sEnabled, setK8sEnabled] = useState(false);
  const [k8sAuthMode, setK8sAuthMode] = useState('kubeconfig');

  // Prometheus / Loki 启用状态
  const [promEnabled, setPromEnabled] = useState(false);
  const [lokiEnabled, setLokiEnabled] = useState(false);

  useEffect(() => {
    checkStatus();
  }, []);

  const checkStatus = async () => {
    try {
      const res = await onboardingApi.getStatus();
      if (res.data.initialized) {
        navigate('/', { replace: true });
      }
    } catch {
      // ignore
    }
  };

  const handleStep1 = async () => {
    try {
      const values = await step1Form.validateFields();
      if (values.password !== values.confirm_password) {
        message.error('两次密码不一致');
        return;
      }
      setLoading(true);
      await onboardingApi.submitStep1({
        password: values.password,
        email: values.email,
        feishu_user_id: values.feishu_user_id,
      });
      message.success('账户设置完成');
      setCurrentStep(1);
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.response?.data?.detail || '保存失败');
    } finally {
      setLoading(false);
    }
  };

  const handleStep2 = async () => {
    try {
      const values = await step2Form.validateFields();
      setLoading(true);
      await onboardingApi.submitStep2({
        enabled: k8sEnabled,
        ...values,
      });
      message.success('Kubernetes 配置完成');
      setCurrentStep(2);
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.response?.data?.detail || '保存失败');
    } finally {
      setLoading(false);
    }
  };

  const handleStep3 = async () => {
    try {
      const values = await step3Form.validateFields();
      setLoading(true);
      await onboardingApi.submitStep3({
        enabled: promEnabled,
        ...values,
      });
      message.success('Prometheus 配置完成');
      setCurrentStep(3);
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.response?.data?.detail || '保存失败');
    } finally {
      setLoading(false);
    }
  };

  const handleStep4 = async () => {
    try {
      const values = await step4Form.validateFields();
      setLoading(true);
      await onboardingApi.submitStep4({
        enabled: lokiEnabled,
        ...values,
      });
      message.success('Loki 配置完成');
      await handleComplete();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.response?.data?.detail || '保存失败');
    } finally {
      setLoading(false);
    }
  };

  const handleComplete = async () => {
    try {
      await onboardingApi.complete();
      setCompleted(true);
      setTimeout(() => navigate('/', { replace: true }), 2000);
    } catch {
      message.error('完成初始化失败');
    }
  };

  if (completed) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <Result
          status="success"
          title="初始化完成"
          subTitle="系统配置已保存，即将跳转到主页面"
        />
      </div>
    );
  }

  const stepTitles = [
    { title: '账户设置', icon: <UserOutlined /> },
    { title: 'Kubernetes', icon: <CloudServerOutlined /> },
    { title: 'Prometheus', icon: <DashboardOutlined /> },
    { title: 'Loki', icon: <FileSearchOutlined /> },
  ];

  const stepDescriptions = [
    '设置管理员密码、邮箱和飞书 ID',
    '配置 Kubernetes 集群连接（可跳过）',
    '配置 Prometheus 监控（可跳过）',
    '配置 Loki 日志（可跳过）',
  ];

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5' }}>
      <Card style={{ width: 640, boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <Title level={3} style={{ marginBottom: 8 }}>🚀 系统初始化</Title>
          <Text type="secondary">首次使用，请完成以下配置</Text>
        </div>

        <Steps current={currentStep} size="small" style={{ marginBottom: 40 }}>
          {stepTitles.map((s, i) => (
            <Steps.Step key={i} title={s.title} icon={s.icon} />
          ))}
        </Steps>

        {/* Step 1: 账户设置 */}
        {currentStep === 0 && (
          <>
            <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>{stepDescriptions[0]}</Text>
            <Form form={step1Form} layout="vertical" size="large">
              <Form.Item name="password" label="新密码" rules={[
                { required: true, message: '请输入密码' },
                { min: 8, message: '密码至少 8 个字符' },
              ]}>
                <Input.Password placeholder="至少 8 个字符，包含字母和数字" />
              </Form.Item>
              <Form.Item name="confirm_password" label="确认密码" rules={[
                { required: true, message: '请确认密码' },
              ]}>
                <Input.Password placeholder="再次输入密码" />
              </Form.Item>
              <Form.Item name="email" label="邮箱" rules={[
                { required: true, message: '请输入邮箱' },
                { type: 'email', message: '邮箱格式不正确' },
              ]}>
                <Input placeholder="admin@example.com" />
              </Form.Item>
              <Form.Item name="feishu_user_id" label="飞书 User ID" rules={[
                { required: true, message: '请输入飞书 User ID' },
              ]} extra="用于接收飞书通知，格式如 ou_xxx 或 gf_xxx">
                <Input placeholder="ou_xxx 或 gf_xxx" />
              </Form.Item>
            </Form>
            <div style={{ textAlign: 'right' }}>
              <Button type="primary" loading={loading} onClick={handleStep1}>
                下一步
              </Button>
            </div>
          </>
        )}

        {/* Step 2: Kubernetes */}
        {currentStep === 1 && (
          <>
            <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>{stepDescriptions[1]}</Text>
            <Form form={step2Form} layout="vertical" size="large">
              <Form.Item label="启用 Kubernetes">
                <Switch checked={k8sEnabled} onChange={setK8sEnabled} />
              </Form.Item>
              {k8sEnabled && (
                <>
                  <Form.Item name="api_host" label="API 地址" rules={[{ required: k8sEnabled }]}>
                    <Input placeholder="https://your-k8s-api:6443" />
                  </Form.Item>
                  <Form.Item name="auth_mode" label="认证方式" initialValue="kubeconfig">
                    <Select onChange={setK8sAuthMode}>
                      <Select.Option value="kubeconfig">Kubeconfig</Select.Option>
                      <Select.Option value="token">Bearer Token</Select.Option>
                    </Select>
                  </Form.Item>
                  {k8sAuthMode === 'kubeconfig' && (
                    <Form.Item name="kubeconfig" label="Kubeconfig" rules={[{ required: k8sEnabled }]}>
                      <TextArea rows={6} placeholder="粘贴 kubeconfig 内容" style={{ fontFamily: 'monospace' }} />
                    </Form.Item>
                  )}
                  {k8sAuthMode === 'token' && (
                    <Form.Item name="token" label="Bearer Token" rules={[{ required: k8sEnabled }]}>
                      <Input.Password placeholder="Bearer Token" />
                    </Form.Item>
                  )}
                </>
              )}
            </Form>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Button onClick={() => setCurrentStep(0)}>上一步</Button>
              <Space>
                <Button onClick={() => { setCurrentStep(2); }}>跳过</Button>
                <Button type="primary" loading={loading} onClick={handleStep2}>下一步</Button>
              </Space>
            </div>
          </>
        )}

        {/* Step 3: Prometheus */}
        {currentStep === 2 && (
          <>
            <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>{stepDescriptions[2]}</Text>
            <Form form={step3Form} layout="vertical" size="large">
              <Form.Item label="启用 Prometheus">
                <Switch checked={promEnabled} onChange={setPromEnabled} />
              </Form.Item>
              {promEnabled && (
                <Form.Item name="url" label="Prometheus URL" rules={[{ required: promEnabled }]}>
                  <Input placeholder="http://prometheus:9090" />
                </Form.Item>
              )}
            </Form>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Button onClick={() => setCurrentStep(1)}>上一步</Button>
              <Space>
                <Button onClick={() => { setCurrentStep(3); }}>跳过</Button>
                <Button type="primary" loading={loading} onClick={handleStep3}>下一步</Button>
              </Space>
            </div>
          </>
        )}

        {/* Step 4: Loki */}
        {currentStep === 3 && (
          <>
            <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>{stepDescriptions[3]}</Text>
            <Form form={step4Form} layout="vertical" size="large">
              <Form.Item label="启用 Loki">
                <Switch checked={lokiEnabled} onChange={setLokiEnabled} />
              </Form.Item>
              {lokiEnabled && (
                <Form.Item name="url" label="Loki URL" rules={[{ required: lokiEnabled }]}>
                  <Input placeholder="http://loki:3100" />
                </Form.Item>
              )}
            </Form>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Button onClick={() => setCurrentStep(2)}>上一步</Button>
              <Button type="primary" loading={loading} onClick={handleStep4}>
                完成配置 <CheckCircleOutlined />
              </Button>
            </div>
          </>
        )}
      </Card>
    </div>
  );
};

export default OnboardingWizard;
