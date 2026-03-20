// src/pages/SystemSettings.tsx
import React, { useState, useEffect } from 'react';
import {
  Card,
  Tabs,
  Form,
  Input,
  Switch,
  Button,
  message,
  Space,
  Spin,
  Typography,
  Divider,
  Tag,
} from 'antd';
import { SaveOutlined, ReloadOutlined, ApiOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { settingsApi, GroupedSettings, SystemSetting } from '../api/settings';
import { integrationsAPI, IntegrationTestResponse } from '../api/integrations';

const { Title, Text } = Typography;
const { TabPane } = Tabs;
const { TextArea } = Input;

const SystemSettings: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState<GroupedSettings>({});
  const [activeCategory, setActiveCategory] = useState<string>('');

  // 连接测试状态
  const [testResults, setTestResults] = useState<Record<string, IntegrationTestResponse>>({});
  const [testLoading, setTestLoading] = useState<Record<string, boolean>>({});

  // 加载系统设置
  const loadSettings = async () => {
    setLoading(true);
    try {
      const data = await settingsApi.getAll();
      setSettings(data);

      // 设置默认激活的分类
      const categories = Object.keys(data);
      if (categories.length > 0 && !activeCategory) {
        setActiveCategory(categories[0]);
      }

      // 填充表单
      const formValues: Record<string, any> = {};
      Object.values(data).flat().forEach((setting: SystemSetting) => {
        if (setting.value_type === 'boolean') {
          formValues[setting.key] = setting.value === 'True' || setting.value === 'true';
        } else {
          formValues[setting.key] = setting.value;
        }
      });
      form.setFieldsValue(formValues);
    } catch (error) {
      message.error('加载系统设置失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  // 保存设置
  const handleSave = async () => {
    setSaving(true);
    try {
      const values = form.getFieldsValue();

      // 转换布尔值为字符串
      const settingsToUpdate: Record<string, any> = {};
      Object.entries(values).forEach(([key, value]) => {
        const setting = Object.values(settings)
          .flat()
          .find((s: SystemSetting) => s.key === key);

        if (setting) {
          if (setting.value_type === 'boolean') {
            settingsToUpdate[key] = value ? 'True' : 'False';
          } else {
            settingsToUpdate[key] = value;
          }
        }
      });

      await settingsApi.batchUpdate({ settings: settingsToUpdate });
      message.success('系统设置保存成功');
      loadSettings();
    } catch (error) {
      message.error('保存系统设置失败');
      console.error(error);
    } finally {
      setSaving(false);
    }
  };

  // 重置表单
  const handleReset = () => {
    loadSettings();
    message.info('已重置为当前保存的值');
  };

  // 测试连接
  const testConnection = async (service: 'kubernetes' | 'prometheus' | 'loki' | 'feishu') => {
    setTestLoading({ ...testLoading, [service]: true });
    try {
      let result: IntegrationTestResponse;

      switch (service) {
        case 'kubernetes':
          result = await integrationsAPI.testKubernetes();
          break;
        case 'prometheus':
          result = await integrationsAPI.testPrometheus();
          break;
        case 'loki':
          result = await integrationsAPI.testLoki();
          break;
        case 'feishu':
          result = await integrationsAPI.testFeishu();
          break;
      }

      setTestResults({ ...testResults, [service]: result });

      if (result.success) {
        message.success(`${service} 连接测试成功`);
      } else {
        message.error(`${service} 连接测试失败: ${result.error}`);
      }
    } catch (error: any) {
      console.error(`${service} test error:`, error);
      message.error(`${service} 连接测试失败: ${error.message}`);
    } finally {
      setTestLoading({ ...testLoading, [service]: false });
    }
  };

  // 渲染连接测试按钮和结果
  const renderConnectionTest = (service: 'kubernetes' | 'prometheus' | 'loki' | 'feishu') => {
    const result = testResults[service];
    const loading = testLoading[service];

    return (
      <Space direction="vertical" style={{ width: '100%', marginTop: 8 }}>
        <Button
          size="small"
          icon={<ApiOutlined />}
          onClick={() => testConnection(service)}
          loading={loading}
        >
          测试连接
        </Button>

        {result && (
          <div>
            {result.success ? (
              <Tag icon={<CheckCircleOutlined />} color="success">
                连接成功 {result.response_time_ms && `(${result.response_time_ms.toFixed(0)}ms)`}
              </Tag>
            ) : (
              <Tag icon={<CloseCircleOutlined />} color="error">
                连接失败: {result.error}
              </Tag>
            )}
            {result.version && (
              <div style={{ marginTop: 4, fontSize: 12, color: '#666' }}>
                版本: {result.version}
              </div>
            )}
          </div>
        )}
      </Space>
    );
  };

  // 渲染设置项
  const renderSettingField = (setting: SystemSetting) => {
    const { key, name, description, value_type, is_sensitive, is_readonly, category } = setting;

    // 判断是否需要显示连接测试按钮
    const needsConnectionTest =
      (category === 'kubernetes' && key === 'k8s.kubeconfig') ||
      (category === 'prometheus' && key === 'prometheus.url') ||
      (category === 'loki' && key === 'loki.url') ||
      (category === 'feishu' && key === 'feishu.reject_message');

    const connectionTestService =
      category === 'kubernetes' ? 'kubernetes' :
      category === 'prometheus' ? 'prometheus' :
      category === 'loki' ? 'loki' :
      category === 'feishu' ? 'feishu' : null;

    if (value_type === 'boolean') {
      return (
        <Form.Item
          key={key}
          name={key}
          label={name}
          valuePropName="checked"
          tooltip={description}
        >
          <Switch disabled={is_readonly} />
        </Form.Item>
      );
    }

    if (is_sensitive) {
      return (
        <Form.Item
          key={key}
          name={key}
          label={name}
          tooltip={description}
        >
          <Input.Password
            placeholder={`请输入${name}`}
            disabled={is_readonly}
            autoComplete="new-password"
          />
        </Form.Item>
      );
    }

    if (value_type === 'json') {
      return (
        <Form.Item
          key={key}
          name={key}
          label={name}
          tooltip={description}
        >
          <TextArea
            rows={4}
            placeholder={`请输入${name}（JSON 格式）`}
            disabled={is_readonly}
          />
        </Form.Item>
      );
    }

    return (
      <div key={key}>
        <Form.Item
          name={key}
          label={name}
          tooltip={description}
        >
          <Input
            placeholder={`请输入${name}`}
            disabled={is_readonly}
          />
        </Form.Item>
        {needsConnectionTest && connectionTestService && renderConnectionTest(connectionTestService)}
      </div>
    );
  };

  // 分类名称映射
  const categoryNames: Record<string, string> = {
    llm: 'LLM 参数',
    feishu: '飞书配置',
    features: '功能开关',
    kubernetes: 'Kubernetes',
    prometheus: 'Prometheus',
    loki: 'Loki',
    testing: '测试配置',
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <Spin size="large" tip="加载系统设置中..." />
      </div>
    );
  }

  return (
    <div style={{ padding: '24px' }}>
      <Card>
        <Title level={2}>系统设置</Title>
        <Text type="secondary">
          配置系统的运行时参数，修改后点击保存按钮即可立即生效，无需重启服务。
        </Text>

        <Divider style={{ marginTop: 24 }} />

        <Form
          form={form}
          layout="vertical"
          onFinish={handleSave}
        >
          <Tabs
            activeKey={activeCategory}
            onChange={setActiveCategory}
            type="card"
          >
            {Object.entries(settings).map(([category, categorySettings]) => (
              <TabPane
                tab={categoryNames[category] || category}
                key={category}
              >
                <div style={{ maxWidth: 800 }}>
                  {categorySettings.map((setting: SystemSetting) =>
                    renderSettingField(setting)
                  )}
                </div>
              </TabPane>
            ))}
          </Tabs>

          <Divider />

          <Space>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={saving}
              onClick={handleSave}
            >
              保存设置
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleReset}
              disabled={saving}
            >
              重置
            </Button>
          </Space>
        </Form>
      </Card>
    </div>
  );
};

export default SystemSettings;
