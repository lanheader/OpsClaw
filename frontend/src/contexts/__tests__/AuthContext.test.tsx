// src/contexts/__tests__/AuthContext.test.tsx
/**
 * AuthContext 测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { AuthProvider, useAuth } from '../AuthContext';
import * as authApi from '@/api/auth';
import * as authUtils from '@/utils/auth';

// Mock API 和工具函数
vi.mock('@/api/auth');
vi.mock('@/utils/auth');
vi.mock('antd', () => ({
  message: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('AuthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(authUtils.getToken).mockReturnValue(null);
    vi.mocked(authUtils.getStoredUser).mockReturnValue(null);
  });

  describe('useAuth hook', () => {
    it('should throw error when used outside AuthProvider', () => {
      expect(() => {
        renderHook(() => useAuth());
      }).toThrow('useAuth must be used within an AuthProvider');
    });

    it('should provide auth context', () => {
      const { result } = renderHook(() => useAuth(), {
        wrapper: AuthProvider,
      });

      expect(result.current).toHaveProperty('user');
      expect(result.current).toHaveProperty('token');
      expect(result.current).toHaveProperty('login');
      expect(result.current).toHaveProperty('logout');
      expect(result.current).toHaveProperty('isAuthenticated');
      expect(result.current).toHaveProperty('loading');
    });
  });

  describe('initial state', () => {
    it('should start with no user and not authenticated', async () => {
      const { result } = renderHook(() => useAuth(), {
        wrapper: AuthProvider,
      });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.user).toBeNull();
      expect(result.current.token).toBeNull();
      expect(result.current.isAuthenticated).toBe(false);
    });

    it('should restore user from storage if token exists', async () => {
      const mockUser = {
        id: 1,
        username: 'testuser',
        email: 'test@example.com',
        full_name: 'Test User',
        is_active: true,
        is_superuser: false,
        created_at: '2024-01-01',
        updated_at: '2024-01-01',
        last_login_at: null,
      };

      vi.mocked(authUtils.getToken).mockReturnValue('test-token');
      vi.mocked(authUtils.getStoredUser).mockReturnValue(mockUser);
      vi.mocked(authApi.authApi.getCurrentUser).mockResolvedValue(mockUser);

      const { result } = renderHook(() => useAuth(), {
        wrapper: AuthProvider,
      });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.user).toEqual(mockUser);
      expect(result.current.token).toBe('test-token');
      expect(result.current.isAuthenticated).toBe(true);
    });
  });

  describe('login', () => {
    it('should login successfully', async () => {
      const mockUser = {
        id: 1,
        username: 'testuser',
        email: 'test@example.com',
        full_name: 'Test User',
        is_active: true,
        is_superuser: false,
        created_at: '2024-01-01',
        updated_at: '2024-01-01',
        last_login_at: null,
      };

      const mockLoginResponse = {
        access_token: 'new-token',
        token_type: 'bearer',
        user: mockUser,
      };

      vi.mocked(authApi.authApi.login).mockResolvedValue(mockLoginResponse);

      const { result } = renderHook(() => useAuth(), {
        wrapper: AuthProvider,
      });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      await result.current.login('testuser', 'password', false);

      // 等待状态更新
      await waitFor(() => {
        expect(result.current.user).toEqual(mockUser);
      });

      expect(authUtils.setToken).toHaveBeenCalledWith('new-token');
      expect(authUtils.setStoredUser).toHaveBeenCalledWith(mockUser);
      expect(result.current.token).toBe('new-token');
      expect(result.current.isAuthenticated).toBe(true);
    });
  });

  describe('logout', () => {
    it('should logout successfully', async () => {
      const mockUser = {
        id: 1,
        username: 'testuser',
        email: 'test@example.com',
        full_name: 'Test User',
        is_active: true,
        is_superuser: false,
        created_at: '2024-01-01',
        updated_at: '2024-01-01',
        last_login_at: null,
      };

      vi.mocked(authUtils.getToken).mockReturnValue('test-token');
      vi.mocked(authUtils.getStoredUser).mockReturnValue(mockUser);
      vi.mocked(authApi.authApi.getCurrentUser).mockResolvedValue(mockUser);
      vi.mocked(authApi.authApi.logout).mockResolvedValue();

      const { result } = renderHook(() => useAuth(), {
        wrapper: AuthProvider,
      });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      act(() => {
        result.current.logout();
      });

      // 等待状态更新
      await waitFor(() => {
        expect(result.current.user).toBeNull();
      });

      expect(authUtils.removeToken).toHaveBeenCalled();
      expect(result.current.token).toBeNull();
      expect(result.current.isAuthenticated).toBe(false);
    });
  });
});
