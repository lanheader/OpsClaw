// src/pages/Dashboard.tsx
/**
 * 仪表盘页面
 */
import { useState } from 'react';
import { Row, Col, Card, Statistic, Space, Button, message } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  RocketOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { workflowAPI } from '@/api/workflow';
import { feishuAPI } from '@/api/feishu';

export const Dashboard: React.FC = () => {
  const [refreshing, setRefreshing] = useState(false);

  // 查询系统健康状态
  const { data: healthData, isLoading: healthLoading } = useQuery({
    queryKey: ['health'],
    queryFn: () => workflowAPI.getHealth(),
    refetchInterval: 10000, // 每10秒刷新
  });

  // 查询飞书状态
  const { data: feishuData, refetch: refetchFeishu } = useQuery({
    queryKey: ['feishu-status'],
    queryFn: () => feishuAPI.getStatus(),
    refetchInterval: 30000, // 每30秒刷新
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

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* 统计卡片 */}
      <Row gutter={16}>
        <Col xs={24} sm={12} md={6} lg={6}>
          <Card>
            <Statistic
              title="总工作流数"
              value={0}
              prefix={<RocketOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6} lg={6}>
          <Card>
            <Statistic
              title="执行中"
              value={0}
              prefix={<SyncOutlined spin />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6} lg={6}>
          <Card>
            <Statistic
              title="成功完成"
              value={0}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6} lg={6}>
          <Card>
            <Statistic
              title="执行失败"
              value={0}
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
            loading={healthLoading}
          >
            {healthData && (
              <Space direction="vertical" style={{ width: '100%' }}>
                <div>
                  <strong>版本:</strong> {healthData.version}
                </div>
                <div>
                  <strong>环境:</strong> {healthData.environment}
                </div>
                <div>
                  <strong>LLM 状态:</strong> {healthData.components?.llm || '未知'}
                </div>
              </Space>
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
              <Space direction="vertical" style={{ width: '100%' }}>
                <div>
                  <strong>状态:</strong>{' '}
                  {feishuData.enabled ? (
                    <span style={{ color: '#52c41a' }}>✅ 已启用</span>
                  ) : (
                    <span style={{ color: '#ff4d4f' }}>❌ 未启用</span>
                  )}
                </div>
                {feishuData.enabled && (
                  <>
                    <div>
                      <strong>连接模式:</strong> {feishuData.connection_mode}
                    </div>
                    <div>
                      <strong>健康:</strong>{' '}
                      {feishuData.healthy ? (
                        <span style={{ color: '#52c41a' }}>✅ 正常</span>
                      ) : (
                        <span style={{ color: '#ff4d4f' }}>❌ 异常</span>
                      )}
                    </div>
                    {feishuData.longconn && (
                      <>
                        <div>
                          <strong>长连接:</strong>{' '}
                          {feishuData.longconn.connected ? (
                            <span style={{ color: '#52c41a' }}>✅ 已连接</span>
                          ) : (
                            <span style={{ color: '#ff4d4f' }}>❌ 未连接</span>
                          )}
                        </div>
                        <div>
                          <strong>重连次数:</strong> {feishuData.longconn.reconnect_count}
                        </div>
                      </>
                    )}
                  </>
                )}
              </Space>
            ) : (
              <div>加载中...</div>
            )}
          </Card>
        </Col>
      </Row>

      {/* 最近工作流 */}
      <Card title="最近执行的工作流">
        <div style={{ textAlign: 'center', padding: '40px 0', color: '#999' }}>
          暂无数据
        </div>
      </Card>
    </Space>
  );
};
