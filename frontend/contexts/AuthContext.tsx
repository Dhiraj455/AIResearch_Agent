"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { getToken, setToken, clearToken } from "@/lib/auth-store";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type User = {
  id: string;
  email: string;
};

export type AuthContextValue = {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setTokenState] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchUser = useCallback(async (t: string) => {
    const res = await fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${t}` },
    });
    if (!res.ok) throw new Error("Invalid token");
    const data = await res.json();
    return { id: data.id, email: data.email };
  }, []);

  useEffect(() => {
    const t = getToken();
    if (!t) {
      queueMicrotask(() => setIsLoading(false));
      return;
    }
    fetchUser(t)
      .then((u) => {
        setUser(u);
        setTokenState(t);
      })
      .catch(() => {
        clearToken();
      })
      .finally(() => setIsLoading(false));
  }, [fetchUser]);

  useEffect(() => {
    const handleUnauthorized = () => {
      clearToken();
      setUser(null);
      setTokenState(null);
    };
    window.addEventListener("auth:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", handleUnauthorized);
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Login failed");
      }
      const data = await res.json();
      const t = data.access_token;
      setToken(t);
      const u = await fetchUser(t);
      setUser(u);
      setTokenState(t);
    },
    [fetchUser]
  );

  const register = useCallback(
    async (email: string, password: string) => {
      const res = await fetch(`${API_BASE}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(
          typeof data.detail === "string" ? data.detail : "Registration failed"
        );
      }
      const data = await res.json();
      const t = data.access_token;
      setToken(t);
      const u = await fetchUser(t);
      setUser(u);
      setTokenState(t);
    },
    [fetchUser]
  );

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    setTokenState(null);
  }, []);

  const value: AuthContextValue = {
    user,
    token,
    isLoading,
    isAuthenticated: !!token && !!user,
    login,
    register,
    logout,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
