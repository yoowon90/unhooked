import React, { createContext, useContext, useEffect, useState } from 'react';
import { authApi, User, saveToken, deleteToken, getToken } from '../services/api';

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, firstName: string, password: string, zipcode: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // On startup, check if a token exists and fetch the current user.
    (async () => {
      try {
        const token = await getToken();
        if (token) {
          const me = await authApi.me();
          setUser(me);
        }
      } catch {
        await deleteToken();
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function login(email: string, password: string) {
    const { token, user } = await authApi.login(email, password);
    await saveToken(token);
    setUser(user);
  }

  async function signup(email: string, firstName: string, password: string, zipcode: string) {
    const { token, user } = await authApi.signup(email, firstName, password, zipcode);
    await saveToken(token);
    setUser(user);
  }

  async function logout() {
    await deleteToken();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
