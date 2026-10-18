import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import ChatPage from "@/pages/ChatPage";
import LoginPage from "@/pages/LoginPage";
import ValidationPage from "@/pages/ValidationPage";
import { AuthProvider, useAuth } from "@/components/AuthProvider";
import { useTheme } from "@/hooks/useTheme";
import { DEMO_MODE } from "@/lib/api";
import { MathJaxContext } from "better-react-mathjax";
import { MATHJAX_CONFIG, MATHJAX_SRC } from "@/lib/math";

function RequireAuth({ children }) {
  const { authenticated } = useAuth();
  const location = useLocation();
  if (DEMO_MODE || authenticated) return children;
  return <Navigate to="/login" replace state={{ from: location.pathname }} />;
}

function App() {
  const { theme, toggle } = useTheme();
  return (
    <MathJaxContext version={3} src={MATHJAX_SRC} config={MATHJAX_CONFIG}>
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage theme={theme} onToggleTheme={toggle} />} />
            <Route path="/" element={<RequireAuth><ChatPage theme={theme} onToggleTheme={toggle} /></RequireAuth>} />
            <Route path="/validate" element={<RequireAuth><ValidationPage theme={theme} onToggleTheme={toggle} /></RequireAuth>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
      <Toaster position="bottom-right" theme={theme} toastOptions={{ style: { fontFamily: "inherit", background: "var(--paper)", color: "var(--ink)", borderColor: "var(--rule-2)", boxShadow: "var(--shadow-lg)" } }} />
    </div>
    </MathJaxContext>
  );
}

export default App;
