import { createContext, useContext, useEffect, useState } from "react";
import { api } from "./api";

export type UserInfo = {
  id: number;
  username: string;
  display_name: string;
  role: "admin" | "user";
  tenant_id: number;
  tenant: any;
};

type AuthState = {
  user: UserInfo | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => void;
};

const Ctx = createContext<AuthState>({ user: null, loading: true, refresh: async () => {}, logout: () => {} });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    if (!localStorage.getItem("token")) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const resp = await api<{ data: { user: UserInfo } }>("get", "/me");
      setUser(resp.data.user);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const logout = () => {
    localStorage.removeItem("token");
    setUser(null);
  };

  return <Ctx.Provider value={{ user, loading, refresh, logout }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  return useContext(Ctx);
}
