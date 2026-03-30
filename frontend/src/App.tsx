// src/App.tsx
/**
 * 主应用组件
 */
import { Layout, Menu, Typography, Button, Dropdown, Space } from 'antd';
import {
  DashboardOutlined,
  RocketOutlined,
  HistoryOutlined,
  SettingOutlined,
  UserOutlined,
  LogoutOutlined,
  TeamOutlined,
  SafetyOutlined,
  MessageOutlined,
  EditOutlined,
} from '@ant-design/icons';
import { BrowserRouter, Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Dashboard } from './pages/Dashboard';
import { WorkflowExecute } from './pages/WorkflowExecute';
import { WorkflowDetail } from './pages/WorkflowDetail';
import { Login } from './pages/Login';
import { UserManagement } from './pages/UserManagement';
import { RoleManagement } from './pages/RoleManagement';
import { ApprovalConfigManagement } from './pages/ApprovalConfigManagement';
import SystemSettings from './pages/SystemSettings';
import Chat from './pages/Chat';
import Profile from './pages/Profile';
import PromptManagement from './pages/PromptManagement';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { PermissionProvider, usePermission } from './contexts/PermissionContext';
import { PrivateRoute } from './components/PrivateRoute';

const { Header, Content, Sider } = Layout;
const { Title } = Typography;

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const AppLayout: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { hasPermission, loading: permissionLoading } = usePermission();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const userMenuItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人信息',
      onClick: () => navigate('/profile'),
    },
    {
      type: 'divider' as const,
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: handleLogout,
    },
  ];

  // 使用 useMemo 或直接在渲染时计算，确保权限变化时重新计算
  const menuItems = [
    hasPermission('view_dashboard') && {
      key: '/',
      icon: <DashboardOutlined />,
      label: <Link to="/">仪表盘</Link>,
    },
    hasPermission('execute_workflow') && {
      key: '/execute',
      icon: <RocketOutlined />,
      label: <Link to="/execute">执行工作流</Link>,
    },
    {
      key: '/chat',
      icon: <MessageOutlined />,
      label: <Link to="/chat">AI 对话</Link>,
    },
    hasPermission('view_history') && {
      key: '/history',
      icon: <HistoryOutlined />,
      label: <Link to="/history">执行历史</Link>,
    },
    hasPermission('manage_users') && {
      key: '/users',
      icon: <TeamOutlined />,
      label: <Link to="/users">用户管理</Link>,
    },
    hasPermission('manage_roles') && {
      key: '/roles',
      icon: <SafetyOutlined />,
      label: <Link to="/roles">角色权限</Link>,
    },
    hasPermission('manage_roles') && {
      key: '/approval-config',
      icon: <SafetyOutlined />,
      label: <Link to="/approval-config">审批配置</Link>,
    },
    hasPermission('view_settings') && {
      key: '/settings',
      icon: <SettingOutlined />,
      label: <Link to="/settings">系统设置</Link>,
    },
    hasPermission('manage_roles') && {
      key: '/prompts',
      icon: <EditOutlined />,
      label: <Link to="/prompts">提示词管理</Link>,
    },
  ].filter((item): item is { key: string; icon: JSX.Element; label: JSX.Element } => Boolean(item));

  // 权限加载中时显示加载状态
  if (permissionLoading) {
    return (
      <Layout style={{ minHeight: '100vh', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
        <div>加载中...</div>
      </Layout>
    );
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#001529' }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{ color: 'white', fontSize: 20, fontWeight: 'bold', marginRight: 40 }}>
            🤖 Ops Agent v3.0
          </div>
          <Title level={5} style={{ color: 'white', margin: 0 }}>
            智能运维管理平台
          </Title>
        </div>
        <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
          <Button type="text" style={{ color: 'white' }}>
            <Space>
              <UserOutlined />
              {user?.username || '用户'}
            </Space>
          </Button>
        </Dropdown>
      </Header>
      <Layout>
        <Sider width={200} style={{ background: '#fff' }}>
          <Menu
            mode="inline"
            selectedKeys={[location.pathname]}
            style={{ height: '100%', borderRight: 0 }}
            items={menuItems}
          />
        </Sider>
        <Content
          style={{
            margin: 0,
            minHeight: 280,
            background: '#fff',
          }}
        >
          <div className={location.pathname.startsWith('/chat') ? 'content-no-padding' : ''} style={{
            padding: location.pathname.startsWith('/chat') ? 0 : 24,
          }}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/execute" element={<WorkflowExecute />} />
              <Route path="/workflow/:taskId" element={<WorkflowDetail />} />
              <Route path="/chat" element={<Chat />} />
              <Route path="/chat/:sessionId" element={<Chat />} />
              <Route path="/history" element={<div>执行历史（待实现）</div>} />
              <Route path="/users" element={<UserManagement />} />
              <Route path="/roles" element={<RoleManagement />} />
              <Route path="/approval-config" element={<ApprovalConfigManagement />} />
              <Route path="/profile" element={<Profile />} />
              <Route path="/settings" element={<SystemSettings />} />
              <Route path="/prompts" element={<PromptManagement />} />
            </Routes>
          </div>
        </Content>
      </Layout>
    </Layout>
  );
};

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <PermissionProvider>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/*" element={
                <PrivateRoute>
                  <AppLayout />
                </PrivateRoute>
              } />
            </Routes>
          </PermissionProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
};
