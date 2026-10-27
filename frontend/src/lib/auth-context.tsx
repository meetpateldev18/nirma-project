import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import * as api from '@/lib/api-client';

interface AuthUser {
  name: string;
  role: api.StaffRole;
  institute_code?: string;
  institute_id?: number;
  department_code?: string;
  department_id?: number;
  program_id?: number;
  division_id?: number;
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
    return stored
      ? {
          name: stored.name,
          role: stored.role,
          institute_code: stored.institute_code,
          institute_id: stored.institute_id,
          department_code: stored.department_code,
          department_id: stored.department_id,
          program_id: stored.program_id,
          division_id: stored.division_id,
        }
      : null;
  });

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await api.login(email, password);
    setUser({
      name: tokens.name,
      role: tokens.role,
      institute_code: tokens.institute_code,
      institute_id: tokens.institute_id,
      department_code: tokens.department_code,
      department_id: tokens.department_id,
      program_id: tokens.program_id,
      division_id: tokens.division_id,
    });
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
