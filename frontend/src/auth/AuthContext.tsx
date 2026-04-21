import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from 'react';
import { api, User } from '../api/client';

interface AuthCtx {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthCtx>({} as AuthCtx);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    const raw = localStorage.getItem('shift_user');
    return raw ? JSON.parse(raw) : null;
  });
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('shift_token'));
  const [loading, setLoading] = useState<boolean>(!!token);

  // Validate stored token on mount
  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .get('/auth/me')
      .then((r) => {
        setUser(r.data);
        localStorage.setItem('shift_user', JSON.stringify(r.data));
      })
      .catch(() => {
        setUser(null);
        setToken(null);
        localStorage.removeItem('shift_token');
        localStorage.removeItem('shift_user');
      })
      .finally(() => setLoading(false));
  }, []); // run once

  const login = useCallback(async (email: string, password: string) => {
    const r = await api.post('/auth/login-json', { email, password });
    const t: string = r.data.access_token;
    const u: User = r.data.user;
    localStorage.setItem('shift_token', t);
    localStorage.setItem('shift_user', JSON.stringify(u));
    setToken(t);
    setUser(u);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('shift_token');
    localStorage.removeItem('shift_user');
    setToken(null);
    setUser(null);
  }, []);

  return <Ctx.Provider value={{ user, token, loading, login, logout }}>{children}</Ctx.Provider>;
}
