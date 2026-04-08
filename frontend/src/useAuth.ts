import { useState, useCallback, useEffect } from 'react';
import * as api from './api';

const TOKEN_KEY = 'parana_auth_token';

export interface UseAuthReturn {
  token: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => void;
  error: string | null;
}

export function useAuth(): UseAuthReturn {
  const [token, setToken] = useState<string | null>(() => {
    return localStorage.getItem(TOKEN_KEY);
  });
  const [error, setError] = useState<string | null>(null);

  const login = useCallback(async (username: string, password: string) => {
    setError(null);
    try {
      const data = await api.login(username, password);
      setToken(data.access_token);
      localStorage.setItem(TOKEN_KEY, data.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
      throw err;
    }
  }, []);

  const register = useCallback(async (username: string, password: string) => {
    setError(null);
    try {
      await api.register(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
      throw err;
    }
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    localStorage.removeItem(TOKEN_KEY);
  }, []);

  return {
    token,
    isAuthenticated: !!token,
    login,
    register,
    logout,
    error,
  };
}
