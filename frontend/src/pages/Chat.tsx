// src/pages/Chat.tsx
/**
 * AI 对话页面
 */
import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Layout,
  List,
  Button,
  Input,
  Card,
  Avatar,
  Spin,
  message as antMessage,
  Modal,
  Empty
} from 'antd';
import {
  MessageOutlined,
  SendOutlined,
  PlusOutlined,
  DeleteOutlined,
  RobotOutlined,
  UserOutlined,
  WechatOutlined
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { chatApi, ChatSession, ChatMessage } from '@/api/chat';
import { useAuth } from '@/contexts/AuthContext';
import './Chat.css';

const { Sider, Content } = Layout;
const { TextArea } = Input;

const Chat: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  // 状态管理
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSession, setCurrentSession] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [statusMessage, setStatusMessage] = useState(''); // 新增：状态消息
  const [approvalRequest, setApprovalRequest] = useState<{
    message: string;
    commands: any[];
    sessionId: string;
  } | null>(null); // 新增：批准请求状态

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const streamingContentRef = useRef<string>('');

  // 自动滚动到底部
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingContent]);

  // 加载会话列表
  const loadSessions = async () => {
    try {
      const data = await chatApi.getSessions();
      setSessions(data.sessions);
    } catch (error) {
      console.error('Failed to load sessions:', error);
      antMessage.error('加载会话列表失败');
    }
  };

  // 加载消息历史
  const loadMessages = async (sid: string) => {
    try {
      setIsLoading(true);
      const data = await chatApi.getMessages(sid);
      setMessages(data);
    } catch (error) {
      console.error('Failed to load messages:', error);
      antMessage.error('加载消息历史失败');
    } finally {
      setIsLoading(false);
    }
  };

  // 创建新会话
  const handleCreateSession = async () => {
    try {
      const newSession = await chatApi.createSession();
      setSessions([newSession, ...sessions]);
      navigate(`/chat/${newSession.session_id}`);
      antMessage.success('创建会话成功');
    } catch (error) {
      console.error('Failed to create session:', error);
      antMessage.error('创建会话失败');
    }
  };

  // 删除会话
  const handleDeleteSession = (sid: string) => {
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除这个会话吗？此操作不可恢复。',
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await chatApi.deleteSession(sid);
          setSessions(sessions.filter(s => s.session_id !== sid));

          // 如果删除的是当前会话，跳转到首页
          if (sid === sessionId) {
            navigate('/chat');
          }

          antMessage.success('删除会话成功');
        } catch (error) {
          console.error('Failed to delete session:', error);
          antMessage.error('删除会话失败');
        }
      }
    });
  };

  // 发送消息
  const handleSendMessage = async () => {
    if (!inputValue.trim() || !sessionId) {
      return;
    }

    const userMessage = inputValue.trim();
    setInputValue('');
    setIsStreaming(true);
    setStreamingContent('');
    setStatusMessage(''); // 重置状态消息
    streamingContentRef.current = ''; // 重置 ref

    // 乐观更新：立即显示用户消息
    const tempUserMessage: ChatMessage = {
      id: Date.now(),
      role: 'user',
      content: userMessage,
      created_at: new Date().toISOString()
    };
    setMessages(prev => [...prev, tempUserMessage]);

    try {
      const controller = await chatApi.sendMessageStream(
        sessionId,
        userMessage,
        (chunk) => {
          // 接收流式内容
          streamingContentRef.current += chunk; // 更新 ref
          setStreamingContent(prev => prev + chunk);
        },
        (_status, message) => {
          // 接收状态更新
          setStatusMessage(message);
        },
        (message, commands, sid) => {
          // 接收批准请求
          setApprovalRequest({ message, commands, sessionId: sid });
          setStatusMessage('⏸️ 等待您的确认...');
        },
        (messageId) => {
          // 流式完成
          setIsStreaming(false);
          setStatusMessage(''); // 清除状态消息

          // 将流式内容添加到消息列表（使用 ref 的值）
          if (streamingContentRef.current) {
            const assistantMessage: ChatMessage = {
              id: messageId || Date.now(),
              role: 'assistant',
              content: streamingContentRef.current, // 使用 ref 的值
              created_at: new Date().toISOString()
            };
            setMessages(prev => [...prev, assistantMessage]);
          }
          setStreamingContent('');
          streamingContentRef.current = ''; // 重置 ref

          // 重新加载会话列表（更新 last_message）
          loadSessions();
        },
        (error) => {
          // 错误处理
          setIsStreaming(false);
          setStreamingContent('');
          setStatusMessage(''); // 清除状态消息
          streamingContentRef.current = ''; // 重置 ref
          antMessage.error(`发送失败: ${error.message}`);
        }
      );

      abortControllerRef.current = controller;

    } catch (error) {
      setIsStreaming(false);
      setStreamingContent('');
      setStatusMessage(''); // 清除状态消息
      console.error('Failed to send message:', error);
      antMessage.error('发送消息失败');
    }
  };

  // 处理批准决定
  const handleApprovalDecision = async (approved: boolean) => {
    if (!approvalRequest) return;

    const { sessionId: sid } = approvalRequest;
    setApprovalRequest(null); // 关闭对话框
    setIsStreaming(true);
    setStatusMessage(approved ? '✅ 已批准，继续执行...' : '❌ 已拒绝');

    try {
      const controller = await chatApi.resumeWorkflow(
        sid,
        approved ? 'approved' : 'rejected',
        (chunk) => {
          // 接收流式内容
          streamingContentRef.current += chunk;
          setStreamingContent(prev => prev + chunk);
        },
        (_status, message) => {
          // 接收状态更新
          setStatusMessage(message);
        },
        (message, commands, sessionId) => {
          // 可能有多个批准点
          setApprovalRequest({ message, commands, sessionId });
          setStatusMessage('⏸️ 等待您的确认...');
        },
        () => {
          // 完成
          setIsStreaming(false);
          setStatusMessage('');

          // 将流式内容添加到消息列表
          if (streamingContentRef.current) {
            const assistantMessage: ChatMessage = {
              id: Date.now(),
              role: 'assistant',
              content: streamingContentRef.current,
              created_at: new Date().toISOString()
            };
            setMessages(prev => [...prev, assistantMessage]);
          }
          setStreamingContent('');
          streamingContentRef.current = '';

          // 重新加载会话列表
          loadSessions();
        },
        (error) => {
          // 错误处理
          setIsStreaming(false);
          setStreamingContent('');
          setStatusMessage('');
          streamingContentRef.current = '';
          antMessage.error(`恢复工作流失败: ${error.message}`);
        }
      );

      abortControllerRef.current = controller;

    } catch (error) {
      setIsStreaming(false);
      setStreamingContent('');
      setStatusMessage('');
      console.error('Failed to resume workflow:', error);
      antMessage.error('恢复工作流失败');
    }
  };

  // 处理键盘事件（Enter 发送，Shift+Enter 换行）
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // 初始化：加载会话列表
  useEffect(() => {
    loadSessions();

    // 定时刷新会话列表（每10秒）
    const intervalId = setInterval(() => {
      loadSessions();
    }, 10000); // 10秒

    // 清理定时器
    return () => {
      clearInterval(intervalId);
    };
  }, []);

  // 当 sessionId 变化时，加载消息历史
  useEffect(() => {
    if (sessionId) {
      loadMessages(sessionId);

      // 从会话列表中找到当前会话
      const session = sessions.find(s => s.session_id === sessionId);
      setCurrentSession(session || null);
    } else {
      setMessages([]);
      setCurrentSession(null);
    }
  }, [sessionId]);

  // 渲染消息气泡
  const renderMessage = (msg: ChatMessage) => {
    const isUser = msg.role === 'user';

    return (
      <div
        key={msg.id}
        style={{
          display: 'flex',
          justifyContent: isUser ? 'flex-end' : 'flex-start',
          marginBottom: 16
        }}
      >
        <div
          style={{
            maxWidth: '70%',
            display: 'flex',
            flexDirection: isUser ? 'row-reverse' : 'row',
            gap: 8
          }}
        >
          <Avatar
            icon={isUser ? <UserOutlined /> : <RobotOutlined />}
            style={{
              backgroundColor: isUser ? '#1890ff' : '#52c41a',
              flexShrink: 0
            }}
          />
          <Card
            size="small"
            style={{
              backgroundColor: isUser ? '#e6f7ff' : '#f0f0f0',
              border: 'none'
            }}
            bodyStyle={{ padding: '12px 16px' }}
          >
            {isUser ? (
              <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
            ) : (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {msg.content}
              </ReactMarkdown>
            )}
            <div style={{ fontSize: 12, color: '#999', marginTop: 8 }}>
              {new Date(msg.created_at).toLocaleTimeString()}
            </div>
          </Card>
        </div>
      </div>
    );
  };

  return (
    <Layout style={{ height: '100vh' }}>
      {/* 左侧会话列表 */}
      <Sider width={280} theme="light" style={{ borderRight: '1px solid #f0f0f0', display: 'flex', flexDirection: 'column', height: '100vh' }}>
        <div style={{ padding: 16, flexShrink: 0 }}>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            block
            onClick={handleCreateSession}
          >
            新建对话
          </Button>
        </div>

        <div className="session-list-container" style={{ maxHeight: 'calc(100vh - 80px)' }}>
        <List
          dataSource={sessions}
          renderItem={(session) => (
            <List.Item
              key={session.session_id}
              style={{
                padding: '12px 16px',
                cursor: 'pointer',
                backgroundColor: session.session_id === sessionId ? '#e6f7ff' : 'transparent'
              }}
              onClick={() => navigate(`/chat/${session.session_id}`)}
              actions={
                // 显示删除按钮的条件：
                // 1. 管理员可以删除任何会话
                // 2. 普通用户只能删除自己创建的 Web 会话
                (user?.is_superuser || (session.source === 'web')) ? [
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteSession(session.session_id);
                    }}
                  />
                ] : []
              }
            >
              <List.Item.Meta
                avatar={
                  session.source === 'feishu' ? (
                    <WechatOutlined style={{ fontSize: 20, color: '#52c41a' }} />
                  ) : (
                    <MessageOutlined style={{ fontSize: 20 }} />
                  )
                }
                title={
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span>
                      {session.source === 'feishu' && session.external_user_name
                        ? `${session.external_user_name} - ${session.title || '飞书对话'}`
                        : session.source === 'web' && session.username
                        ? `${session.username} - ${session.title || '新对话'}`
                        : session.title || '新对话'}\n                    </span>
                    {session.source === 'feishu' && (
                      <span style={{
                        fontSize: 12,
                        color: '#52c41a',
                        backgroundColor: '#f6ffed',
                        padding: '2px 8px',
                        borderRadius: 4,
                        border: '1px solid #b7eb8f'
                      }}>
                        飞书
                      </span>
                    )}
                  </div>
                }
                description={
                  <div style={{ fontSize: 12, color: '#999' }}>
                    {session.last_message || '暂无消息'}
                  </div>
                }
              />
            </List.Item>
          )}
          locale={{ emptyText: <Empty description="暂无会话" /> }}
        />
        </div>
      </Sider>

      {/* 右侧聊天区域 */}
      <Content style={{ display: 'flex', flexDirection: 'column' }}>
        {sessionId ? (
          <>
            {/* 消息列表 */}
            <div
              style={{
                flex: 1,
                overflowY: 'auto',
                padding: 24,
                backgroundColor: '#fafafa'
              }}
            >
              {isLoading ? (
                <div style={{ textAlign: 'center', padding: 48 }}>
                  <Spin size="large" />
                </div>
              ) : (
                <>
                  {messages.map(renderMessage)}

                  {/* 状态消息 */}
                  {isStreaming && statusMessage && !streamingContent && (
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'flex-start',
                        marginBottom: 16
                      }}
                    >
                      <div style={{ maxWidth: '70%', display: 'flex', gap: 8 }}>
                        <Avatar
                          icon={<RobotOutlined />}
                          style={{ backgroundColor: '#52c41a', flexShrink: 0 }}
                        />
                        <Card
                          size="small"
                          style={{ backgroundColor: '#e6f7ff', border: '1px solid #91d5ff' }}
                          bodyStyle={{ padding: '12px 16px' }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <Spin size="small" />
                            <span>{statusMessage}</span>
                          </div>
                        </Card>
                      </div>
                    </div>
                  )}

                  {/* 流式消息 */}
                  {isStreaming && streamingContent && (
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'flex-start',
                        marginBottom: 16
                      }}
                    >
                      <div style={{ maxWidth: '70%', display: 'flex', gap: 8 }}>
                        <Avatar
                          icon={<RobotOutlined />}
                          style={{ backgroundColor: '#52c41a', flexShrink: 0 }}
                        />
                        <Card
                          size="small"
                          style={{ backgroundColor: '#f0f0f0', border: 'none' }}
                          bodyStyle={{ padding: '12px 16px' }}
                        >
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {streamingContent}
                          </ReactMarkdown>
                          <Spin size="small" style={{ marginLeft: 8 }} />
                        </Card>
                      </div>
                    </div>
                  )}

                  <div ref={messagesEndRef} />
                </>
              )}
            </div>

            {/* 输入区域 */}
            <div
              style={{
                padding: 16,
                borderTop: '1px solid #f0f0f0',
                backgroundColor: '#fff'
              }}
            >
              {currentSession?.source === 'feishu' ? (
                // 飞书会话只读提示
                <div style={{
                  textAlign: 'center',
                  padding: '12px',
                  backgroundColor: '#f6ffed',
                  border: '1px solid #b7eb8f',
                  borderRadius: 4,
                  color: '#52c41a'
                }}>
                  <WechatOutlined style={{ marginRight: 8 }} />
                  这是飞书会话，只能在飞书中回复
                </div>
              ) : (
                // Web 会话输入框
                <div style={{ display: 'flex', gap: 8 }}>
                  <TextArea
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
                    autoSize={{ minRows: 1, maxRows: 6 }}
                    disabled={isStreaming}
                    style={{ flex: 1 }}
                  />
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    onClick={handleSendMessage}
                    disabled={!inputValue.trim() || isStreaming}
                    loading={isStreaming}
                  >
                    发送
                  </Button>
                </div>
              )}
            </div>
          </>
        ) : (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%'
            }}
          >
            <Empty
              description="请选择或创建一个会话"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            >
              <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateSession}>
                创建新对话
              </Button>
            </Empty>
          </div>
        )}
      </Content>

      {/* 批准请求 Modal */}
      <Modal
        title="📋 命令执行确认"
        open={approvalRequest !== null}
        onOk={() => handleApprovalDecision(true)}
        onCancel={() => handleApprovalDecision(false)}
        okText="✅ 批准执行"
        cancelText="❌ 拒绝执行"
        width={700}
        maskClosable={false}
      >
        {approvalRequest && (
          <div>
            <div style={{ marginBottom: 16, whiteSpace: 'pre-wrap' }}>
              {approvalRequest.message}
            </div>
            {approvalRequest.commands && approvalRequest.commands.length > 0 && (
              <div>
                <div style={{ fontWeight: 'bold', marginBottom: 8 }}>计划执行的命令：</div>
                <div style={{ background: '#f5f5f5', padding: 12, borderRadius: 4 }}>
                  {approvalRequest.commands.map((cmd, idx) => (
                    <div key={idx} style={{ marginBottom: 8 }}>
                      <div style={{ fontWeight: 'bold' }}>
                        {idx + 1}. {cmd.type}: {cmd.action}
                      </div>
                      {cmd.reason && (
                        <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
                          💡 {cmd.reason}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>
    </Layout>
  );
};

export default Chat;
