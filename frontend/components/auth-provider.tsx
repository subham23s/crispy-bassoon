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
const SESSION_RESTORE_TIMEOUT_MS = 8000;

function getStoredSession(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem(SESSION_KEY) || sessionStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

function setStoredSession(val: string): void {
  if (typeof window === 'undefined') return;
  try { localStorage.setItem(SESSION_KEY, val); } catch {}
  try { sessionStorage.setItem(SESSION_KEY, val); } catch {}
}

function removeStoredSession(): void {
  if (typeof window === 'undefined') return;
  try { localStorage.removeItem(SESSION_KEY); } catch {}
  try { sessionStorage.removeItem(SESSION_KEY); } catch {}
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const clearAuth = useCallback(() => {
    setUser(null);
    removeStoredSession();
  }, []);
  const persistSession = useCallback((tokens: { access_token: string; refresh_token: string } | null) => {
    if (tokens) setStoredSession(JSON.stringify(tokens));
    else removeStoredSession();
  }, []);
  const api = useMemo(() => new ApiClient(undefined, clearAuth, persistSession), [clearAuth, persistSession]);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    let timeout: ReturnType<typeof setTimeout> | undefined;
    async function restore() {
      try {
        const raw = getStoredSession();
        if (!raw) return;
        const tokens = JSON.parse(raw) as { access_token?: string; refresh_token?: string };
        api.setSession(tokens);
        const timedOut = new Promise<never>((_, reject) => {
          timeout = setTimeout(() => {
            controller.abort();
            reject(new Error('Session restore timed out.'));
          }, SESSION_RESTORE_TIMEOUT_MS);
        });
        const result = await Promise.race([api.me(controller.signal), timedOut]);
        if (active) setUser(result.user);
      } catch {
        if (active) {
          api.clearSession();
          removeStoredSession();
        }
      } finally {
        clearTimeout(timeout);
        if (active) setLoading(false);
      }
    }
    restore();
    return () => { active = false; clearTimeout(timeout); controller.abort(); };
  }, [api]);

  const signIn = useCallback(async (email: string, password: string, register = false) => {
    const result = register ? await api.register(email, password) : await api.login(email, password);
    setStoredSession(JSON.stringify({ access_token: result.access_token, refresh_token: result.refresh_token }));
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
