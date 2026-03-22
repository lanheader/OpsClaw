// src/pages/Diagnostics.tsx
/**
 * 诊断页面 - 用于测试 API 连接
 */
import { useState } from 'react';
import { Card, Button, Space, Alert, Descriptions, Tag, Row, Col } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, SyncOutlined } from '@ant-design/icons';
import { workflowAPI } from '@/api/workflow';
import { feishuAPI } from '@/api/feishu';
import { llmAPI, LLMTestResponse } from '@/api/llm';

// 健康状态类型定义
interface HealthStatus {
  status: string;
  version: string;
  environment: string;
  [key: string]: any;
}

// 飞书状态类型定义
interface FeishuStatus {
  enabled: boolean;
  connection_mode?: string;
  healthy?: boolean;
  [key: string]: any;
}

export const Diagnostics: React.FC = () => {
  const [healthStatus, setHealthStatus] = useState<HealthStatus | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);

  const [feishuStatus, setFeishuStatus] = useState<FeishuStatus | null>(null);
  const [feishuError, setFeishuError] = useState<string | null>(null);
  const [feishuLoading, setFeishuLoading] = useState(false);

  // LLM 测试状态
  const [llmResults, setLlmResults] = useState<Record<string, LLMTestResponse>>({});
  const [llmLoading, setLlmLoading] = useState<Record<string, boolean>>({});

  const testHealth = async () => {
    setHealthLoading(true);
    setHealthError(null);
    try {
      const data = await workflowAPI.getHealth();
      setHealthStatus(data);
    } catch (error: unknown) {
      setHealthError(error instanceof Error ? error.message : '请求失败');
      console.error('Health check error:', error);
    } finally {
      setHealthLoading(false);
    }
  };

  const testFeishu = async () => {
    setFeishuLoading(true);
    setFeishuError(null);
    try {
      const data = await feishuAPI.getStatus();
      setFeishuStatus(data);
    } catch (error: any) {
      setFeishuError(error.message || '请求失败');
      console.error('Feishu status error:', error);
    } finally {
      setFeishuLoading(false);
    }
  };

  const testLLM = async (provider: 'openai' | 'claude' | 'zhipu' | 'ollama' | 'openrouter') => {
    setLlmLoading({ ...llmLoading, [provider]: true });
    try {
      const result = await llmAPI.test({ provider });
      setLlmResults({ ...llmResults, [provider]: result });
    } catch (error: unknown) {
      console.error(`LLM test error for ${provider}:`, error);
      setLlmResults({
        ...llmResults,
        [provider]: {
          success: false,
          provider,
          model: 'unknown',
          error: error instanceof Error ? error.message : '请求失败',
        },
      });
    } finally {
      setLlmLoading({ ...llmLoading, [provider]: false });
    }
  };

  const testAllLLMs = async () => {
    await Promise.all([
      testLLM('openai'),
      testLLM('claude'),
      testLLM('zhipu'),
      testLLM('ollama'),
      testLLM('openrouter'),
    ]);
  };

  const renderLLMResult = (provider: string) => {
    const result = llmResults[provider];
    const loading = llmLoading[provider];

    if (!result && !loading) {
      return null;
    }

    if (loading) {
      return <Tag icon={<SyncOutlined spin />} color="processing">测试中...</Tag>;
    }

    if (result.success) {
      return (
        <Descriptions bordered column={1} size="small">
          <Descriptions.Item label="状态">
            <Tag color="success" icon={<CheckCircleOutlined />}>连接成功</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="模型">{result.model}</Descriptions.Item>
          <Descriptions.Item label="响应时间">
            {result.response_time_ms?.toFixed(2)} ms
          </Descriptions.Item>
          <Descriptions.Item label="测试响应">
            {result.test_message}
          </Descriptions.Item>
        </Descriptions>
      );
    } else {
      return (
        <Alert
          message="连接失败"
          description={result.error}
          type="error"
          showIcon
          icon={<CloseCircleOutlined />}
        />
      );
    }
  };

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Alert
        message="API 连接诊断"
        description="此页面用于测试前端与后端 API 的连接是否正常"
        type="info"
        showIcon
      />

      {/* 健康检查测试 */}
      <Card
        title="健康检查 API"
        extra={
          <Button
            type="primary"
            icon={<SyncOutlined />}
            onClick={testHealth}
            loading={healthLoading}
          >
            测试
          </Button>
        }
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <div>
            <strong>端点:</strong> GET /api/v2/health
          </div>

          {healthError && (
            <Alert
              message="请求失败"
              description={healthError}
              type="error"
              showIcon
              icon={<CloseCircleOutlined />}
            />
          )}

          {healthStatus && (
            <>
              <Alert
                message="请求成功"
                type="success"
                showIcon
                icon={<CheckCircleOutlined />}
              />
              <Descriptions bordered column={1}>
                <Descriptions.Item label="状态">
                  <Tag color="success">{healthStatus.status}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="版本">
                  {healthStatus.version}
                </Descriptions.Item>
                <Descriptions.Item label="环境">
                  {healthStatus.environment}
                </Descriptions.Item>
                <Descriptions.Item label="LLM">
                  {healthStatus.components?.llm || '未知'}
                </Descriptions.Item>
              </Descriptions>
            </>
          )}
        </Space>
      </Card>

      {/* LLM 模型测试 */}
      <Card
        title="LLM 模型测试"
        extra={
          <Button
            type="primary"
            icon={<SyncOutlined />}
            onClick={testAllLLMs}
            loading={Object.values(llmLoading).some(Boolean)}
          >
            测试所有模型
          </Button>
        }
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <div>
            <strong>说明:</strong> 测试各个 LLM 提供商的连接状态
          </div>

          <Row gutter={[16, 16]}>
            <Col span={12}>
              <Card
                size="small"
                title="OpenAI"
                extra={
                  <Button
                    size="small"
                    icon={<SyncOutlined />}
                    onClick={() => testLLM('openai')}
                    loading={llmLoading['openai']}
                  >
                    测试
                  </Button>
                }
              >
                {renderLLMResult('openai')}
              </Card>
            </Col>

            <Col span={12}>
              <Card
                size="small"
                title="Claude"
                extra={
                  <Button
                    size="small"
                    icon={<SyncOutlined />}
                    onClick={() => testLLM('claude')}
                    loading={llmLoading['claude']}
                  >
                    测试
                  </Button>
                }
              >
                {renderLLMResult('claude')}
              </Card>
            </Col>

            <Col span={12}>
              <Card
                size="small"
                title="智谱 AI"
                extra={
                  <Button
                    size="small"
                    icon={<SyncOutlined />}
                    onClick={() => testLLM('zhipu')}
                    loading={llmLoading['zhipu']}
                  >
                    测试
                  </Button>
                }
              >
                {renderLLMResult('zhipu')}
              </Card>
            </Col>

            <Col span={12}>
              <Card
                size="small"
                title="Ollama"
                extra={
                  <Button
                    size="small"
                    icon={<SyncOutlined />}
                    onClick={() => testLLM('ollama')}
                    loading={llmLoading['ollama']}
                  >
                    测试
                  </Button>
                }
              >
                {renderLLMResult('ollama')}
              </Card>
            </Col>

            <Col span={12}>
              <Card
                size="small"
                title="OpenRouter"
                extra={
                  <Button
                    size="small"
                    icon={<SyncOutlined />}
                    onClick={() => testLLM('openrouter')}
                    loading={llmLoading['openrouter']}
                  >
                    测试
                  </Button>
                }
              >
                {renderLLMResult('openrouter')}
              </Card>
            </Col>
          </Row>
        </Space>
      </Card>

      {/* 飞书状态测试 */}
      <Card
        title="飞书状态 API"
        extra={
          <Button
            type="primary"
            icon={<SyncOutlined />}
            onClick={testFeishu}
            loading={feishuLoading}
          >
            测试
          </Button>
        }
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <div>
            <strong>端点:</strong> GET /api/v1/feishu/status
          </div>

          {feishuError && (
            <Alert
              message="请求失败"
              description={feishuError}
              type="error"
              showIcon
              icon={<CloseCircleOutlined />}
            />
          )}

          {feishuStatus && (
            <>
              <Alert
                message="请求成功"
                type="success"
                showIcon
                icon={<CheckCircleOutlined />}
              />
              <Descriptions bordered column={1}>
                <Descriptions.Item label="启用状态">
                  {feishuStatus.enabled ? (
                    <Tag color="success">已启用</Tag>
                  ) : (
                    <Tag color="default">未启用</Tag>
                  )}
                </Descriptions.Item>
                {feishuStatus.enabled && (
                  <>
                    <Descriptions.Item label="连接模式">
                      {feishuStatus.connection_mode}
                    </Descriptions.Item>
                    <Descriptions.Item label="健康状态">
                      {feishuStatus.healthy ? (
                        <Tag color="success">健康</Tag>
                      ) : (
                        <Tag color="error">异常</Tag>
                      )}
                    </Descriptions.Item>
                  </>
                )}
              </Descriptions>
            </>
          )}
        </Space>
      </Card>

      {/* 浏览器信息 */}
      <Card title="浏览器信息">
        <Descriptions bordered column={1}>
          <Descriptions.Item label="User Agent">
            {navigator.userAgent}
          </Descriptions.Item>
          <Descriptions.Item label="当前 URL">
            {window.location.href}
          </Descriptions.Item>
          <Descriptions.Item label="API Base URL">
            {import.meta.env.VITE_API_BASE_URL || '/api'}
          </Descriptions.Item>
        </Descriptions>
      </Card>
    </Space>
  );
};
