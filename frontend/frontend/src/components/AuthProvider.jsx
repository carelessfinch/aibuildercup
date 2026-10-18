import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { API_BASE, DEMO_MODE } from "@/lib/api";
import { clearAuth, getAuth, setAuth } from "@/lib/auth";

const AuthContext = createContext(null);

async function parseError(res) {
  try {
    const body = await res.json();
    return body.detail || `Login failed (${res.status})`;
  } catch {
    return `Login failed (${res.status})`;
  }
}

export function AuthProvider({ children }) {
  const navigate = useNavigate();
  const [auth, setAuthState] = useState(() => (DEMO_MODE ? null : getAuth()));

  useEffect(() => {
    const expired = () => {
      setAuthState(null);
      navigate("/login", { replace: true });
    };
    const changed = () => setAuthState(DEMO_MODE ? null : getAuth());
    window.addEventListener("plasma:auth-expired", expired);
    window.addEventListener("plasma:auth-changed", changed);
    return () => {
      window.removeEventListener("plasma:auth-expired", expired);
      window.removeEventListener("plasma:auth-changed", changed);
    };
  }, [navigate]);

  const login = useCallback(async (username, password) => {
    const res = await fetch(`${API_BASE}/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: username.trim(), password }),
    });
    if (!res.ok) throw new Error(await parseError(res));
    const payload = await res.json();
    const nextAuth = {
      token: payload.token,
      username: payload.username || username.trim(),
      expires_at: payload.expires_at,
    };
    setAuth(nextAuth);
    setAuthState(nextAuth);
  }, []);

  const logout = useCallback(() => {
    clearAuth(false);
    setAuthState(null);
    navigate("/login", { replace: true });
  }, [navigate]);

  const value = useMemo(() => ({
    user: DEMO_MODE ? { username: "Demo" } : auth,
    authenticated: DEMO_MODE || Boolean(auth),
    login,
    logout,
  }), [auth, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
