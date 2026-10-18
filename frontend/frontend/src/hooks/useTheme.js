import { useCallback, useEffect, useState } from "react";

const KEY = "rag_theme";

const initial = () => {
  const stored = localStorage.getItem(KEY);
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
};

export function useTheme() {
  const [theme, setTheme] = useState(initial);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    localStorage.setItem(KEY, theme);
  }, [theme]);

  const toggle = useCallback(() => setTheme((t) => (t === "dark" ? "light" : "dark")), []);
  return { theme, toggle };
}
