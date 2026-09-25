"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import {
  clearTokenCookie,
  readTokenCookie,
  writeTokenCookie,
  type AuthUser,
} from "@/lib/auth";
import { saveProfile } from "@/lib/profile";

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<AuthUser>;
  register: (name: string, email: string, password: string) => Promise<AuthUser>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    void (async () => {
      await Promise.resolve();
      if (!readTokenCookie()) {
        if (active) setLoading(false);
        return;
      }
      try {
        const me = await api.me();
        if (active) {
          setUser(me);
          saveProfile({ name: me.name, email: me.email, role: "Trader" });
        }
      } catch {
        clearTokenCookie();
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const applyAuth = useCallback(
    (token: string, nextUser: AuthUser) => {
      writeTokenCookie(token);
      setUser(nextUser);
      saveProfile({ name: nextUser.name, email: nextUser.email, role: "Trader" });
      router.refresh();
    },
    [router],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      const response = await api.login({ email, password });
      applyAuth(response.token, response.user);
      return response.user;
    },
    [applyAuth],
  );

  const register = useCallback(
    async (name: string, email: string, password: string) => {
      const response = await api.register({ name, email, password });
      applyAuth(response.token, response.user);
      return response.user;
    },
    [applyAuth],
  );

  const logout = useCallback(() => {
    clearTokenCookie();
    setUser(null);
    router.push("/login");
    router.refresh();
  }, [router]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
