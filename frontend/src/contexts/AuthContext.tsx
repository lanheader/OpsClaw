// src/contexts/AuthContext.tsx
import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { authApi, User } from '../api/auth';
import { getToken, setToken, removeToken, getStoredUser, setStoredUser } from '../utils/auth';
import { message } from 'antd';

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (username: string, password: string, remember: boolean) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setTokenState] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const initAuth = async () => {
      const storedToken = getToken();
      const storedUser = getStoredUser();

      if (storedToken && storedUser) {
        try {
          const currentUser = await authApi.getCurrentUser();
          setUser(currentUser);
          setTokenState(storedToken);
        } catch (err) {
          removeToken();
        }
      }

      setLoading(false);
    };

    initAuth();
  }, []);

  const login = async (username: string, password: string, remember: boolean) => {
    const response = await authApi.login({ username, password, remember });
    setToken(response.access_token);
    setStoredUser(response.user);
    setUser(response.user);
    setTokenState(response.access_token);
    message.success('登录成功');
  };

  const logout = () => {
    authApi.logout().catch(() => {});
    removeToken();
    setUser(null);
    setTokenState(null);
    message.success('已退出登录');
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        login,
        logout,
        isAuthenticated: !!token,
        loading
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
