import { useState, useCallback, useEffect } from "react";

const KEY = "rag_chat_sessions";

function load() {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function persist(sessions) {
  localStorage.setItem(KEY, JSON.stringify(sessions));
}

// Local, browser-side chat history. The RAG API has no "list sessions" endpoint,
// so we track session ids + titles here and restore each via GET /v1/sessions.
export function useChatSessions() {
  const [sessions, setSessions] = useState(load);

  useEffect(() => { persist(sessions); }, [sessions]);

  const upsert = useCallback((entry) => {
    setSessions((prev) => {
      const idx = prev.findIndex((s) => s.id === entry.id);
      const clean = Object.fromEntries(Object.entries(entry).filter(([, v]) => v !== undefined));
      if (idx === -1) return [{ title: "New conversation", ...clean }, ...prev];
      const next = [...prev];
      next[idx] = { ...next[idx], ...clean };
      // bump to top on update
      const [item] = next.splice(idx, 1);
      return [item, ...next];
    });
  }, []);

  const remove = useCallback((id) => {
    setSessions((prev) => prev.filter((s) => s.id !== id));
  }, []);

  const rename = useCallback((id, title) => {
    setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, title } : s)));
  }, []);

  return { sessions, upsert, remove, rename };
}

export function groupSessions(sessions) {
  const now = new Date();
  const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const today = startOfDay(now);
  const yesterday = today - 86400000;
  const weekAgo = today - 7 * 86400000;

  const groups = { Today: [], Yesterday: [], "Previous 7 Days": [], Older: [] };
  for (const s of sessions) {
    const t = s.updatedAt || 0;
    if (t >= today) groups.Today.push(s);
    else if (t >= yesterday) groups.Yesterday.push(s);
    else if (t >= weekAgo) groups["Previous 7 Days"].push(s);
    else groups.Older.push(s);
  }
  return Object.entries(groups).filter(([, arr]) => arr.length > 0);
}
