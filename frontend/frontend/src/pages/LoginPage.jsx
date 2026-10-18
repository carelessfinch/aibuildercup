import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { FlaskConical, Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/components/AuthProvider";
import { DEMO_MODE } from "@/lib/api";
import { LOGIN } from "@/constants/testIds";

export default function LoginPage({ theme, onToggleTheme }) {
  const { authenticated, login } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (DEMO_MODE || authenticated) return <Navigate to={location.state?.from || "/"} replace />;

  const submit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      await login(username, password);
      navigate(location.state?.from || "/", { replace: true });
    } catch (e) {
      setError(e.message || "Invalid username or password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-dvh items-center justify-center px-4 py-8" style={{ background: "var(--paper-2)" }}>
      <button type="button" onClick={onToggleTheme} aria-label={theme === "dark" ? "Use light mode" : "Use dark mode"} className="absolute right-4 top-4 icon-btn h-10 w-10" style={{ paddingTop: "env(safe-area-inset-top)" }}>
        {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </button>
      <main className="w-full max-w-[400px] rounded-2xl border p-5 sm:p-7" style={{ background: "var(--paper)", borderColor: "var(--rule-2)", boxShadow: "var(--shadow-lg)" }}>
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl" style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>
            <FlaskConical className="h-5 w-5" />
          </span>
          <div>
            <h1 className="font-serif-read text-[20px] font-semibold leading-tight" style={{ color: "var(--ink)" }}>Plasma Research Group</h1>
            <p className="text-[13px]" style={{ color: "var(--ink-3)" }}>Sign in to continue</p>
          </div>
        </div>

        <form onSubmit={submit} className="mt-6 space-y-4">
          <div>
            <Label htmlFor={LOGIN.usernameInput} className="text-[13px]" style={{ color: "var(--ink-2)" }}>Username</Label>
            <Input
              id={LOGIN.usernameInput}
              data-testid={LOGIN.usernameInput}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              autoCapitalize="none"
              spellCheck="false"
              required
              className="mt-1.5 h-11 rounded-md"
              style={{ background: "var(--paper)", color: "var(--ink)", borderColor: "var(--rule-2)" }}
            />
          </div>
          <div>
            <Label htmlFor={LOGIN.passwordInput} className="text-[13px]" style={{ color: "var(--ink-2)" }}>Password</Label>
            <Input
              id={LOGIN.passwordInput}
              data-testid={LOGIN.passwordInput}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              className="mt-1.5 h-11 rounded-md"
              style={{ background: "var(--paper)", color: "var(--ink)", borderColor: "var(--rule-2)" }}
            />
          </div>
          {error && <p data-testid="login-error" role="alert" className="rounded-md px-3 py-2 text-[13px]" style={{ background: "var(--escalate-soft)", color: "var(--escalate)" }}>{error}</p>}
          <Button type="submit" data-testid={LOGIN.submitButton} disabled={loading} className="h-11 w-full rounded-lg text-[14px] font-semibold" style={{ background: "var(--accent)", color: "var(--paper)" }}>
            {loading ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        <p className="mt-5 text-center text-[12.5px] leading-relaxed" style={{ color: "var(--ink-3)" }}>
          Access is limited to invited demo users. Your signed token lasts 12 hours.
        </p>
      </main>
    </div>
  );
}
