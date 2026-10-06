'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { ApiClient } from '@/lib/api-client';
import type { User } from '@/types/api';

interface AuthContextValue {
  api: ApiClient;
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string, register?: boolean) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const SESSION_KEY = 'cybersecra-x-session';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const clearAuth = useCallback(() => {
    setUser(null);
    if (typeof window !== 'undefined') sessionStorage.removeItem(SESSION_KEY);
  }, []);
  const persistSession = useCallback((tokens: { access_token: string; refresh_token: string } | null) => {
    if (typeof window === 'undefined') return;
    if (tokens) sessionStorage.setItem(SESSION_KEY, JSON.stringify(tokens));
    else sessionStorage.removeItem(SESSION_KEY);
  }, []);
  const api = useMemo(() => new ApiClient(undefined, clearAuth, persistSession), [clearAuth, persistSession]);

  useEffect(() => {
    let active = true;
    async function restore() {
      try {
        const raw = sessionStorage.getItem(SESSION_KEY);
        if (!raw) return;
        const tokens = JSON.parse(raw) as { access_token?: string; refresh_token?: string };
        api.setSession(tokens);
        const result = await api.me();
        if (active) setUser(result.user);
      } catch {
        api.clearSession();
        sessionStorage.removeItem(SESSION_KEY);
      } finally {
        if (active) setLoading(false);
      }
    }
    restore();
    return () => { active = false; };
  }, [api]);

  const signIn = useCallback(async (email: string, password: string, register = false) => {
    const result = register ? await api.register(email, password) : await api.login(email, password);
    if (typeof window !== 'undefined') sessionStorage.setItem(SESSION_KEY, JSON.stringify({ access_token: result.access_token, refresh_token: result.refresh_token }));
    const profile = result.user ? { user: result.user } : await api.me();
    setUser(profile.user ?? null);
  }, [api]);

  const signOut = useCallback(async () => {
    try { await api.logout(); } catch { api.clearSession(); } finally { clearAuth(); }
  }, [api, clearAuth]);

  return <AuthContext.Provider value={{ api, user, loading, signIn, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
