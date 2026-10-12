import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import * as api from '@/lib/api-client';

interface AuthUser {
  name: string;
  role: 'admin' | 'operator';
}

interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(() => {
    const stored = api.loadStoredTokens();
    return stored ? { name: stored.name, role: stored.role } : null;
  });

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await api.login(email, password);
    setUser({ name: tokens.name, role: tokens.role });
  }, []);

  const logout = useCallback(() => {
    api.logout();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, isAuthenticated: !!user, login, logout }),
    [user, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
