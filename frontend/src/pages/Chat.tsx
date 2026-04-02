// src/pages/Chat.tsx
/**
 * AI 对话页面 - 深度美化版
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Layout,
  List,
  Button,
  Input,
  Spin,
  message as antMessage,
  Modal,
  Empty,
  Tooltip,
  Card
} from 'antd';
import {
  MessageOutlined,
  SendOutlined,
  PlusOutlined,
  DeleteOutlined,
  RobotOutlined,
  UserOutlined,
  WechatOutlined,
  ThunderboltOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined
} from '@ant-design/icons';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { chatApi, ChatSession, ChatMessage } from '@/api/chat';
import { useAuth } from '@/contexts/AuthContext';
import './Chat.css';

const { Sider, Content } = Layout;
const { TextArea } = Input;

// 审批命令类型定义
interface ApprovalCommand {
  type: string;
  action: string;
  reason?: string;
}

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
  const [statusMessage, setStatusMessage] = useState('');
  const [approvalRequest, setApprovalRequest] = useState<{
    message: string;
    commands: ApprovalCommand[];
    sessionId: string;
  } | null>(null);

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const streamingContentRef = useRef<string>('');
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // 自动滚动到底部
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
    console.log('📝 Messages updated:', messages.length, messages.map(m => ({ id: m.id, role: m.role, content: m.content.substring(0, 30) })));
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
  const loadMessages = useCallback(async (sid: string) => {
    try {
      setIsLoading(true);
      const data = await chatApi.getMessages(sid);
      console.log('📢 Loaded messages:', data.length, 'for session:', sid);
      setMessages(data);

      // 🔧 检查最后一条助手消息是否是审批请求
      // 如果会话状态是 awaiting_approval，从消息中恢复审批数据
      const lastAssistantMessage = [...data].reverse().find(m => m.role === 'assistant');
      if (lastAssistantMessage?.metadata?.type === 'approval_request') {
        const approvalData = lastAssistantMessage.metadata;
        setApprovalRequest({
          message: approvalData.message || lastAssistantMessage.content.replace(/## 📋 命令规划\n\n/, '').replace(/\n\n$/, ''),
          commands: approvalData.commands || [],
          sessionId: sid
        });
        setIsStreaming(false);
        setStatusMessage('⏸️ 等待您的确认...');
      }
    } catch (error) {
      console.error('Failed to load messages:', error);
      antMessage.error('加载消息历史失败');
    } finally {
      setIsLoading(false);
    }
  }, []);

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
    setStatusMessage('');
    streamingContentRef.current = '';

    // 乐观更新
    const tempUserMessage: ChatMessage = {
      id: Date.now(),
      role: 'user',
      content: userMessage,
      created_at: new Date().toISOString()
    };
    setMessages(prev => [...prev, tempUserMessage]);
    const prevMsgCount = messages.length + 1; // 用户消息发送后应有 N+1 条

    try {
      setIsStreaming(true);
      setStatusMessage('🤖 Agent 正在分析您的请求...');

      await chatApi.sendMessage(sessionId, userMessage);
      // API 立即返回，后台处理中。轮询消息列表获取助手回复。
      const pollInterval = setInterval(async () => {
        try {
          const data = await chatApi.getMessages(sessionId);
          if (data.messages && data.messages.length > prevMsgCount) {
            clearInterval(pollInterval);
            // 添加新消息
            const newMsgs = data.messages.slice(prevMsgCount);
            newMsgs.forEach((msg: ChatMessage) => {
              setMessages(prev => [...prev, msg]);
            });
            setIsStreaming(false);
            setStatusMessage('');
            loadSessions();
          }
        } catch {
          // 忽略轮询错误
        }
      }, 2000);
      // 最多轮询 5 分钟后停止
      setTimeout(() => { clearInterval(pollInterval); setIsStreaming(false); setStatusMessage(''); }, 300000);

    } catch (error) {
      setIsStreaming(false);
      setStatusMessage('');
      console.error('Failed to send message:', error);
      antMessage.error('发送消息失败');
    }

    } catch (error) {
      setIsStreaming(false);
      setStreamingContent('');
      setStatusMessage('');
      streamingContentRef.current = '';
      console.error('Failed to send message:', error);
      antMessage.error('发送消息失败');
    }
  };

  // 处理批准决定
  const handleApprovalDecision = async (approved: boolean) => {
    if (!approvalRequest) return;

    const { sessionId: sid } = approvalRequest;
    setApprovalRequest(null);
    setIsStreaming(true);
    setStatusMessage(approved ? '✅ 已批准，继续执行...' : '❌ 已拒绝');

    try {
      const controller = await chatApi.resumeWorkflow(
        sid,
        approved ? 'approved' : 'rejected',
        (chunk) => {
          streamingContentRef.current += chunk;
          setStreamingContent(prev => prev + chunk);
        },
        (_status, message) => {
          setStatusMessage(message);
        },
        (message, commands, sessionId) => {
          setApprovalRequest({ message, commands, sessionId });
          setStatusMessage('⏸️ 等待您的确认...');
        },
        () => {
          setIsStreaming(false);
          setStatusMessage('');

          if (streamingContentRef.current) {
            // 如果有流式内容，直接添加
            const assistantMessage: ChatMessage = {
              id: Date.now(),
              role: 'assistant',
              content: streamingContentRef.current,
              created_at: new Date().toISOString()
            };
            setMessages(prev => [...prev, assistantMessage]);
          } else {
            // 如果没有流式内容，从服务器重新加载消息
            if (sessionId) {
              loadMessages(sessionId);
            }
          }
          setStreamingContent('');
          streamingContentRef.current = '';
          loadSessions();
        },
        (error) => {
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

  // 处理键盘事件
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // 初始化
  useEffect(() => {
    loadSessions();
    const intervalId = setInterval(() => {
      loadSessions();
    }, 10000);
    return () => {
      clearInterval(intervalId);
    };
  }, []);

  // 当 sessionId 变化时加载消息
  useEffect(() => {
    console.log('🔄 Session useEffect triggered, sessionId:', sessionId);
    if (sessionId) {
      loadMessages(sessionId);

      // 同时获取会话详情（确保 currentSession 正确设置）
      chatApi.getSession(sessionId)
        .then(session => {
          setCurrentSession(session);

          // 🔧 恢复会话状态
          if (session.state === 'awaiting_approval' && session.pending_approval_data) {
            // 恢复审批请求状态
            const approvalData = session.pending_approval_data;
            setApprovalRequest({
              message: approvalData.message || '需要您的确认',
              commands: approvalData.commands || [],
              sessionId: session.session_id
            });
            setIsStreaming(false);
            setStatusMessage('⏸️ 等待您的确认...');
          } else if (session.state === 'processing') {
            // 恢复处理中状态
            setIsStreaming(true);
            setStatusMessage('⏳ 处理中...');
          } else {
            // 正常状态，清除任何残留状态
            setApprovalRequest(null);
            setIsStreaming(false);
            setStatusMessage('');
          }

          // 更新 sessions 列表中的该会话
          setSessions(currentSessions => {
            const exists = currentSessions.some(s => s.session_id === sessionId);
            if (!exists) {
              return [...currentSessions, session];
            }
            return currentSessions.map(s =>
              s.session_id === sessionId ? session : s
            );
          });
        })
        .catch(error => {
          console.error('Failed to load session details:', error);
          // 如果获取失败，尝试从列表中查找
          setSessions(currentSessions => {
            const session = currentSessions.find(s => s.session_id === sessionId);
            setCurrentSession(session || null);
            return currentSessions;
          });
        });
    } else {
      setMessages([]);
      setCurrentSession(null);
      setApprovalRequest(null);
      setIsStreaming(false);
      setStatusMessage('');
    }
  }, [sessionId, loadMessages]);

  // 格式化时间
  const formatTime = (dateString: string | Date): string => {
    let date: Date;

    if (typeof dateString === 'string') {
      if (dateString.includes('T') && !dateString.includes('Z')) {
        dateString = dateString + 'Z';
      }
      date = new Date(dateString);
    } else if (dateString instanceof Date) {
      date = dateString;
    } else {
      return '未知时间';
    }

    if (isNaN(date.getTime())) {
      return '时间解析失败';
    }

    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return '刚刚';
    if (diffMins < 60) return `${diffMins}分钟前`;
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)}小时前`;

    const year = date.getFullYear();
    const nowYear = now.getFullYear();

    if (year !== nowYear) {
      return date.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    }

    return date.toLocaleDateString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // 渲染消息气泡
  const renderMessage = (msg: ChatMessage, _index: number) => {
    const isUser = msg.role === 'user';

    return (
      <div
        key={msg.id}
        className={`chat-message ${isUser ? 'user-message' : 'assistant-message'}`}
      >
        <div className="message-bubble-wrapper">
          <div className={`message-avatar ${isUser ? 'user-avatar' : 'assistant-avatar'}`}>
            {isUser ? <UserOutlined /> : <RobotOutlined />}
          </div>
          <div className={`message-bubble ${isUser ? 'user-bubble' : 'assistant-bubble'}`}>
            <div className="message-content">
              {isUser ? (
                <span>{msg.content}</span>
              ) : (
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={
                    {
                      code: (props: any) => {
                        if (props.inline || !props.className) {
                          return <code className="inline-code">{props.children}</code>;
                        }
                        return <code className={props.className}>{props.children}</code>;
                      },
                      pre: ({ children }: any) => (
                        <div className="code-block-wrapper">{children}</div>
                      ),
                      p: ({ children }: any) => {
                        const hasCodeBlock = React.Children.toArray(children).some(
                          (child: any) =>
                            child?.props?.className?.includes('code-block-wrapper') ||
                            child?.type === 'div'
                        );
                        if (hasCodeBlock) {
                          return <div className="markdown-paragraph">{children}</div>;
                        }
                        return <p>{children}</p>;
                      },
                      ul: ({ children }: any) => <ul className="markdown-list">{children}</ul>,
                      ol: ({ children }: any) => <ol className="markdown-list">{children}</ol>,
                      li: ({ children }: any) => <li>{children}</li>,
                      strong: ({ children }: any) => <strong className="markdown-strong">{children}</strong>,
                      em: ({ children }: any) => <em>{children}</em>,
                    } as Components
                  }
                >
                  {msg.content}
                </ReactMarkdown>
              )}
            </div>
            <div className="message-time">
              <ClockCircleOutlined />
              {formatTime(msg.created_at)}
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <Layout className="chat-layout">
      {/* 左侧会话列表 */}
      <Sider width={320} className="chat-sider">
        <div className="sider-header">
          <div className="header-title">
            <ThunderboltOutlined />
            <span>OpsClaw</span>
          </div>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            className="new-chat-btn"
            onClick={handleCreateSession}
          >
            新建对话
          </Button>
        </div>

        <div className="session-list-container">
          <List
            dataSource={sessions}
            renderItem={(session, index) => (
              <div
                key={session.session_id}
                className={`session-item ${session.session_id === sessionId ? 'active' : ''}`}
                style={{
                  animation: `sessionSlideIn 0.3s ease-out ${index * 0.03}s forwards`,
                  opacity: 0
                }}
                onClick={() => navigate(`/chat/${session.session_id}`)}
              >
                <div className="session-icon">
                  {session.source === 'feishu' ? (
                    <WechatOutlined className="feishu-icon" />
                  ) : (
                    <MessageOutlined />
                  )}
                </div>
                <div className="session-content">
                  <div className="session-title-row">
                    <span className="session-title">
                      {session.source === 'feishu' && session.external_user_name
                        ? session.external_user_name
                        : session.source === 'web' && session.username
                        ? session.username
                        : session.title || '新对话'}
                    </span>
                    {session.source === 'feishu' && (
                      <span className="feishu-badge">飞书</span>
                    )}
                  </div>
                  <div className="session-preview">
                    {session.last_message || '暂无消息'}
                  </div>
                </div>
                {(user?.is_superuser || (session.source === 'web')) && (
                  <Tooltip title="删除会话">
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      className="delete-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteSession(session.session_id);
                      }}
                    />
                  </Tooltip>
                )}
              </div>
            )}
            locale={{ emptyText: <Empty description="暂无会话" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
          />
        </div>
      </Sider>

      {/* 右侧聊天区域 */}
      <Content className="chat-content">
        {sessionId ? (
          <Card
            className="chat-card"
            styles={{ body: { padding: 0, height: '100%', display: 'flex', flexDirection: 'column' } }}
          >
            {/* 消息列表 */}
            <div className="messages-container" style={{ backgroundColor: '#fafafa', minHeight: '200px' }}>
              {isLoading ? (
                <div className="loading-state">
                  <Spin size="large" />
                  <p>加载对话历史...</p>
                </div>
              ) : (
                <>
                  {/* Debug: 消息数量 */}
                  <div style={{ padding: '10px', backgroundColor: '#fff', marginBottom: '10px', borderRadius: '8px' }}>
                    📊 当前会话: {currentSession?.session_id} | 消息数量: {messages.length}
                  </div>
                  {messages.map((msg, idx) => renderMessage(msg, idx))}

                  {/* 状态消息 */}
                  {isStreaming && statusMessage && !streamingContent && (
                    <div className="chat-message assistant-message">
                      <div className="message-bubble-wrapper">
                        <div className="message-avatar assistant-avatar">
                          <RobotOutlined />
                          <span className="avatar-badge">OPS</span>
                        </div>
                        <div className="message-bubble assistant-bubble status-bubble">
                          <div className="status-indicator">
                            <Spin size="small" />
                            <span>{statusMessage}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* 流式消息 */}
                  {isStreaming && streamingContent && (
                    <div className="chat-message assistant-message streaming-message">
                      <div className="message-bubble-wrapper">
                        <div className="message-avatar assistant-avatar">
                          <RobotOutlined />
                          <span className="avatar-badge">OPS</span>
                        </div>
                        <div className="message-bubble assistant-bubble">
                          <div className="message-content">
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              components={
                                {
                                  code: (props: any) => {
                                    if (props.inline || !props.className) {
                                      return <code className="inline-code">{props.children}</code>;
                                    }
                                    return <code className={props.className}>{props.children}</code>;
                                  },
                                  pre: ({ children }: any) => (
                                    <div className="code-block-wrapper">{children}</div>
                                  ),
                                  p: ({ children }: any) => {
                                    const hasCodeBlock = React.Children.toArray(children).some(
                                      (child: any) =>
                                        child?.props?.className?.includes('code-block-wrapper') ||
                                        child?.type === 'div'
                                    );
                                    if (hasCodeBlock) {
                                      return <div className="markdown-paragraph">{children}</div>;
                                    }
                                    return <p>{children}</p>;
                                  },
                                } as Components
                              }
                            >
                              {streamingContent}
                            </ReactMarkdown>
                          </div>
                          <div className="typing-indicator">
                            <span></span>
                            <span></span>
                            <span></span>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  <div ref={messagesEndRef} />
                </>
              )}
            </div>

            {/* 输入区域 */}
            <div className="input-container">
              {currentSession?.source === 'feishu' ? (
                <div className="feishu-notice">
                  <WechatOutlined />
                  <span>这是飞书会话，请在飞书中回复</span>
                </div>
              ) : (
                <div className="input-wrapper">
                  <div className="input-box">
                    <TextArea
                      ref={inputRef}
                      value={inputValue}
                      onChange={(e) => setInputValue(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder="输入消息... (Enter 发送，Shift+Enter 换行)"
                      autoSize={{ minRows: 1, maxRows: 8 }}
                      disabled={isStreaming}
                      className="message-input"
                    />
                    <div className="input-actions">
                      <span className="input-hint">
                        {inputValue.length > 0 && `${inputValue.length} 字符`}
                      </span>
                      <Button
                        type="primary"
                        icon={<SendOutlined />}
                        onClick={handleSendMessage}
                        disabled={!inputValue.trim() || isStreaming}
                        loading={isStreaming}
                        className="send-btn"
                      >
                        发送
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </Card>
        ) : (
          <Card className="chat-card empty-card">
            <Empty
              description={
                <div className="empty-description">
                  <RobotOutlined className="empty-icon" />
                  <h3>欢迎使用 OpsClaw</h3>
                  <p>选择一个会话或创建新对话开始</p>
                </div>
              }
              image={null}
            >
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={handleCreateSession}
                className="create-first-btn"
              >
                创建新对话
              </Button>
            </Empty>
          </Card>
        )}
      </Content>

      {/* 批准请求 Modal */}
      <Modal
        title={
          <div className="approval-modal-title">
            <CheckCircleOutlined />
            <span>命令执行确认</span>
          </div>
        }
        open={approvalRequest !== null}
        onOk={() => handleApprovalDecision(true)}
        onCancel={() => handleApprovalDecision(false)}
        okText="✅ 批准执行"
        cancelText="❌ 拒绝执行"
        width={700}
        maskClosable={false}
        className="approval-modal"
      >
        {approvalRequest && (
          <div className="approval-content">
            <div className="approval-message">{approvalRequest.message}</div>
            {approvalRequest.commands && approvalRequest.commands.length > 0 && (
              <div className="approval-commands">
                <div className="commands-header">
                  <ThunderboltOutlined />
                  <span>计划执行的命令</span>
                </div>
                <div className="commands-list">
                  {approvalRequest.commands.map((cmd, idx) => (
                    <div key={idx} className="command-item">
                      <div className="command-number">{idx + 1}</div>
                      <div className="command-details">
                        <div className="command-type">{cmd.type}</div>
                        <div className="command-action">{cmd.action}</div>
                        {cmd.reason && (
                          <div className="command-reason">
                            <span>💡 </span>
                            {cmd.reason}
                          </div>
                        )}
                      </div>
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
