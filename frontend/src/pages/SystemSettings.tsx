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
} from 'antd';
import { SaveOutlined, ReloadOutlined } from '@ant-design/icons';
import { settingsApi, GroupedSettings, SystemSetting } from '../api/settings';
import KubernetesConfigForm from '../components/KubernetesConfigForm';

const { Text } = Typography;
const { TextArea } = Input;

const SystemSettings: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState<GroupedSettings>({});
  const [activeCategory, setActiveCategory] = useState<string>('');

  // 加载系统设置
  const loadSettings = async () => {
    setLoading(true);
    try {
      const data = await settingsApi.getAll();

      // 过滤掉不需要在页面显示的分类
      const excludedCategories = ['integration', 'kubernetes', 'llm', 'feishu', 'testing', 'features'];
      const filteredData: GroupedSettings = {};
      Object.entries(data).forEach(([category, categorySettings]) => {
        if (!excludedCategories.includes(category)) {
          filteredData[category] = categorySettings;
        }
      });
      setSettings(filteredData);

      // 设置默认激活的分类
      const categories = Object.keys(filteredData);
      if (categories.length > 0 && !activeCategory) {
        setActiveCategory(categories[0]);
      }

      // 填充表单
      const formValues: Record<string, any> = {};
      Object.values(filteredData).flat().forEach((setting: SystemSetting) => {
        if (setting.value_type === 'boolean') {
          formValues[setting.key] = setting.value === '1' || setting.value === 'true' || setting.value === 'True';
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

      // 转换布尔值为 0/1
      const settingsToUpdate: Record<string, any> = {};
      Object.entries(values).forEach(([key, value]) => {
        const setting = Object.values(settings)
          .flat()
          .find((s: SystemSetting) => s.key === key);

        if (setting) {
          if (setting.value_type === 'boolean') {
            settingsToUpdate[key] = value ? '1' : '0';
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

  // 渲染设置项
  const renderSettingField = (setting: SystemSetting) => {
    const { key, name, description, value_type, is_sensitive, is_readonly } = setting;

    if (value_type === 'boolean') {
      return (
        <Form.Item
          key={key}
          name={key}
          label={name}
          valuePropName="checked"
          tooltip={description}
        >
          <Switch checkedChildren="启用" unCheckedChildren="禁用" disabled={is_readonly} />
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
      <Form.Item
        key={key}
        name={key}
        label={name}
        tooltip={description}
      >
        <Input
          placeholder={`请输入${name}`}
          disabled={is_readonly}
        />
      </Form.Item>
    );
  };

  // 分类名称映射
  const categoryNames: Record<string, string> = {
    prometheus: 'Prometheus',
    loki: 'Loki',
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <Spin size="large" tip="加载系统设置中..." />
      </div>
    );
  }

  // 构建 Tabs items
  const tabItems = [
    // Kubernetes 专用 Tab
    {
      key: 'kubernetes',
      label: 'Kubernetes',
      children: <KubernetesConfigForm />,
    },
    // 其他分类的 Tabs
    ...Object.entries(settings).map(([category, categorySettings]) => ({
      key: category,
      label: categoryNames[category] || category,
      children: (
        <div style={{ maxWidth: 800 }}>
          {categorySettings.map((setting: SystemSetting) =>
            renderSettingField(setting)
          )}
        </div>
      ),
    })),
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card
        title="系统设置"
        extra={
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleReset}
              disabled={saving}
            >
              重置
            </Button>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={saving}
              onClick={handleSave}
            >
              保存设置
            </Button>
          </Space>
        }
      >
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
            items={tabItems}
          />
        </Form>
      </Card>
    </Space>
  );
};

export default SystemSettings;
