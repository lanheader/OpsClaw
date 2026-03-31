// src/pages/Dashboard.tsx
/**
 * 仪表盘页面 - 包含系统状态和 API 诊断
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Row, Col, Card, Statistic, Space, Button, message, Descriptions, Tag, Divider, List, Typography, Avatar } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  MessageOutlined,
  UserOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { workflowAPI } from '@/api/workflow';
import { feishuAPI } from '@/api/feishu';
import { llmAPI, LLMTestResponse } from '@/api/llm';
import { chatApi, ChatSession } from '@/api/chat';
import { scheduledTasksApi } from '@/api/scheduledTasks';

const { Text, Paragraph } = Typography;

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [refreshing, setRefreshing] = useState(false);

  // LLM 测试状态
  const [llmResults, setLlmResults] = useState<Record<string, LLMTestResponse>>({});
  const [llmLoading, setLlmLoading] = useState<Record<string, boolean>>({});

  // 查询系统健康状态
  const { data: healthData, isLoading: healthLoading, refetch: refetchHealth } = useQuery({
    queryKey: ['health'],
    queryFn: () => workflowAPI.getHealth(),
    refetchInterval: 30000,
  });

  // 查询飞书状态
  const { data: feishuData, refetch: refetchFeishu } = useQuery({
    queryKey: ['feishu-status'],
    queryFn: () => feishuAPI.getStatus(),
    refetchInterval: 60000,
  });

  // 查询最近会话列表
  const { data: sessionsData, isLoading: sessionsLoading } = useQuery({
    queryKey: ['recent-sessions'],
    queryFn: () => chatApi.getSessions(0, 10),
    refetchInterval: 30000,
  });

  // 查询定时任务统计
  const { data: taskStatsData } = useQuery({
    queryKey: ['task-stats'],
    queryFn: () => scheduledTasksApi.getStats(),
    refetchInterval: 30000,
  });

  const handleTestFeishu = async () => {
    try {
      setRefreshing(true);
      await feishuAPI.sendTestMessage('测试消息来自 OpsClaw Web');
      message.success('测试消息已发送');
      await refetchFeishu();
    } catch (error) {
      message.error('发送失败');
    } finally {
      setRefreshing(false);
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
      return <span style={{ color: '#999' }}>未测试</span>;
    }

    if (loading) {
      return <Tag icon={<SyncOutlined spin />} color="processing">测试中...</Tag>;
    }

    if (result.success) {
      return (
        <Space direction="vertical" size="small">
          <Tag color="success" icon={<CheckCircleOutlined />}>连接成功</Tag>
          <span style={{ fontSize: 12, color: '#666' }}>
            {result.model} ({result.response_time_ms?.toFixed(0)}ms)
          </span>
        </Space>
      );
    } else {
      return <Tag color="error" icon={<CloseCircleOutlined />}>连接失败</Tag>;
    }
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return '刚刚';
    if (minutes < 60) return `${minutes}分钟前`;
    if (hours < 24) return `${hours}小时前`;
    if (days < 7) return `${days}天前`;
    return date.toLocaleDateString();
  };

  const renderSessionItem = (session: ChatSession) => {
    const displayName = session.source === 'feishu'
      ? session.external_user_name || '飞书用户'
      : session.username || 'Web 用户';

    return (
      <List.Item
        style={{ cursor: 'pointer' }}
        onClick={() => navigate(`/chat/${session.session_id}`)}
      >
        <List.Item.Meta
          avatar={
            <Avatar
              icon={session.source === 'feishu' ? <MessageOutlined /> : <UserOutlined />}
              style={{ backgroundColor: session.source === 'feishu' ? '#1890ff' : '#52c41a' }}
            />
          }
          title={
            <Space>
              <Text ellipsis style={{ maxWidth: 200 }}>
                {session.title || '新会话'}
              </Text>
              <Tag color={session.source === 'feishu' ? 'blue' : 'green'} style={{ fontSize: 10 }}>
                {session.source === 'feishu' ? '飞书' : 'Web'}
              </Tag>
              {session.state === 'awaiting_approval' && (
                <Tag color="orange">待审批</Tag>
              )}
              {session.state === 'processing' && (
                <Tag color="processing">处理中</Tag>
              )}
            </Space>
          }
          description={
            <Space split={<Text type="secondary">|</Text>}>
              <Text type="secondary">{displayName}</Text>
              <Text type="secondary">{session.message_count} 条消息</Text>
              <Text type="secondary">
                <ClockCircleOutlined /> {formatTime(session.updated_at)}
              </Text>
            </Space>
          }
        />
        {session.last_message && (
          <Paragraph
            ellipsis={{ rows: 1 }}
            type="secondary"
            style={{ margin: 0, fontSize: 12, maxWidth: 300 }}
          >
            {session.last_message}
          </Paragraph>
        )}
      </List.Item>
    );
  };

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* 统计卡片 */}
      <Row gutter={16}>
        <Col xs={24} sm={12} md={6} lg={6}>
          <Card>
            <Statistic
              title="总任务数"
              value={taskStatsData?.total || 0}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6} lg={6}>
          <Card>
            <Statistic
              title="执行中"
              value={taskStatsData?.running || 0}
              prefix={<SyncOutlined spin />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6} lg={6}>
          <Card>
            <Statistic
              title="成功完成"
              value={taskStatsData?.completed || 0}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6} lg={6}>
          <Card>
            <Statistic
              title="执行失败"
              value={taskStatsData?.failed || 0}
              prefix={<CloseCircleOutlined />}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 系统状态 */}
      <Row gutter={16}>
        <Col xs={24} sm={24} md={12} lg={12}>
          <Card
            title="系统健康状态"
            extra={
              <Button
                type="link"
                icon={<SyncOutlined />}
                onClick={() => refetchHealth()}
                loading={healthLoading}
              >
                刷新
              </Button>
            }
          >
            {healthData && (
              <Descriptions column={1} size="small">
                <Descriptions.Item label="版本">{healthData.version}</Descriptions.Item>
                <Descriptions.Item label="环境">{healthData.environment}</Descriptions.Item>
                <Descriptions.Item label="LLM">
                  {healthData.components?.llm === 'healthy' ? (
                    <Tag color="success">正常</Tag>
                  ) : (
                    <Tag color="error">异常</Tag>
                  )}
                </Descriptions.Item>
              </Descriptions>
            )}
          </Card>
        </Col>

        <Col xs={24} sm={24} md={12} lg={12}>
          <Card
            title="飞书集成状态"
            extra={
              <Button
                type="link"
                onClick={handleTestFeishu}
                loading={refreshing}
                disabled={!feishuData?.enabled}
              >
                发送测试消息
              </Button>
            }
          >
            {feishuData ? (
              <Descriptions column={1} size="small">
                <Descriptions.Item label="状态">
                  {feishuData.enabled ? (
                    <Tag color="success">已启用</Tag>
                  ) : (
                    <Tag color="default">未启用</Tag>
                  )}
                </Descriptions.Item>
                {feishuData.enabled && (
                  <>
                    <Descriptions.Item label="连接模式">{feishuData.connection_mode}</Descriptions.Item>
                    <Descriptions.Item label="健康">
                      {feishuData.healthy ? <Tag color="success">正常</Tag> : <Tag color="error">异常</Tag>}
                    </Descriptions.Item>
                    {feishuData.longconn && (
                      <>
                        <Descriptions.Item label="长连接">
                          {feishuData.longconn.connected ? (
                            <Tag color="success">已连接</Tag>
                          ) : (
                            <Tag color="warning">未连接</Tag>
                          )}
                        </Descriptions.Item>
                      </>
                    )}
                  </>
                )}
              </Descriptions>
            ) : (
              <div>加载中...</div>
            )}
          </Card>
        </Col>
      </Row>

      {/* 最近会话 */}
      <Card
        title="最近会话"
        extra={
          <Button type="link" onClick={() => navigate('/chat')}>
            查看全部
          </Button>
        }
      >
        <List
          loading={sessionsLoading}
          dataSource={sessionsData?.sessions || []}
          renderItem={renderSessionItem}
          locale={{ emptyText: '暂无会话' }}
          style={{ minHeight: 200 }}
        />
      </Card>

      <Divider>API 连接诊断</Divider>

      {/* LLM 模型测试 */}
      <Card
        title="LLM 模型连接测试"
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
        <Row gutter={[16, 16]}>
          {[
            { key: 'openai', label: 'OpenAI' },
            { key: 'claude', label: 'Claude' },
            { key: 'zhipu', label: '智谱 AI' },
            { key: 'ollama', label: 'Ollama' },
            { key: 'openrouter', label: 'OpenRouter' },
          ].map(({ key, label }) => (
            <Col xs={24} sm={12} md={8} lg={8} key={key}>
              <Card
                size="small"
                title={label}
                extra={
                  <Button
                    size="small"
                    icon={<SyncOutlined />}
                    onClick={() => testLLM(key as any)}
                    loading={llmLoading[key]}
                  >
                    测试
                  </Button>
                }
              >
                {renderLLMResult(key)}
              </Card>
            </Col>
          ))}
        </Row>
      </Card>
    </Space>
  );
};
