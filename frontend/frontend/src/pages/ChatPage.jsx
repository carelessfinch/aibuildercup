import { useState, useRef, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useChatSessions } from "@/hooks/useChatSessions";
import { AppShell } from "@/components/chat/AppShell";
import { Composer } from "@/components/chat/Composer";
import { EmptyState } from "@/components/chat/EmptyState";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { SourceViewerPanel } from "@/components/chat/SourceViewerPanel";
import { LiteratureSearchModal } from "@/components/chat/LiteratureSearchModal";

let msgCounter = 0;
const newId = () => `m${Date.now()}_${msgCounter++}`;

const titleFrom = (text) => {
  const t = text.trim().replace(/\s+/g, " ");
  return t.length > 42 ? t.slice(0, 42) + "…" : t;
};

export default function ChatPage({ theme, onToggleTheme }) {
  const { sessions, upsert, remove, rename } = useChatSessions();

  const [agentId, setAgentId] = useState("literature_assistant");
  const [messages, setMessages] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sourceCitation, setSourceCitation] = useState(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [selectedSources, setSelectedSources] = useState([]);

  const abortRef = useRef(null);
  const scrollRef = useRef(null);
  const sessionIdRef = useRef(null);
  const messagesRef = useRef([]);
  messagesRef.current = messages;

  const saveTranscript = useCallback((sid) => {
    if (!sid) return;
    const transcript = messagesRef.current
      .filter((m) => m.content)
      .map(({ id, role, content, citations, agent, model, toolSteps }) => ({
        id, role, content, citations: citations || [], agent, model,
        toolSteps: (toolSteps || []).map((s) => ({ ...s, done: true })),
      }));
    upsert({ id: sid, messages: transcript, updatedAt: Date.now() });
  }, [upsert]);

  useEffect(() => {
    if (messages.length) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const patchAssistant = useCallback((id, updater) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? updater(m) : m)));
  }, []);

  const leaveCurrent = () => {
    if (streaming) {
      saveTranscript(sessionIdRef.current);
      abortRef.current?.abort();
    }
  };

  const startNew = () => {
    leaveCurrent();
    setMessages([]);
    setActiveId(null);
    sessionIdRef.current = null;
    setStreaming(false);
  };

  const selectSession = async (id) => {
    if (id === activeId) return;
    leaveCurrent();
    const local = sessions.find((s) => s.id === id);
    if (local?.messages?.length) {
      setMessages(local.messages.map((m) => ({ ...m, streaming: false })));
      setActiveId(id);
      sessionIdRef.current = id;
      if (local.agent) setAgentId(local.agent);
      return;
    }
    try {
      const data = await api.getSession(id, userId);
      const mapped = (data.messages || []).map((m) => ({
        id: newId(),
        role: m.role,
        content: m.content,
        citations: m.citations || [],
        agent: data.agent || agentId,
        streaming: false,
      }));
      setMessages(mapped);
      setActiveId(id);
      sessionIdRef.current = id;
      if (data.agent) setAgentId(data.agent);
    } catch (e) {
      if (e.status === 404) {
        toast.error("This conversation expired on the server. Starting a new one.");
        remove(id);
        startNew();
      } else {
        toast.error(e.message || "Could not load the conversation");
      }
    }
  };

  const send = async (overrideText) => {
    const text = (overrideText ?? input).trim();
    if (!text || streaming) return;

    const userMsg = { id: newId(), role: "user", content: text };
    const asstId = newId();
    const asstMsg = { id: asstId, role: "assistant", agent: agentId, content: "", citations: [], toolSteps: [], streaming: true };
    setMessages((prev) => [...prev, userMsg, asstMsg]);
    setInput("");
    setStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    const sid = sessionIdRef.current;
    let ownSid = sid;
    const body = { message: text, agent: agentId, session_id: sid };

    const onEvent = (event, data) => {
      if (!data) return;
      if (event === "session") {
        if (data.session_id && data.session_id !== sid) sessionIdRef.current = data.session_id;
        ownSid = sessionIdRef.current;
        const own = ownSid;
        setActiveId(own);
        if (data.model) patchAssistant(asstId, (m) => ({ ...m, model: data.model }));
        upsert({ id: own, title: sid ? undefined : titleFrom(text), agent: data.agent || agentId, updatedAt: Date.now() });
      } else if (event === "tool_call") {
        patchAssistant(asstId, (m) => ({ ...m, toolSteps: [...(m.toolSteps || []), { ...data, done: false }] }));
      } else if (event === "tool_result") {
        patchAssistant(asstId, (m) => {
          const steps = [...(m.toolSteps || [])];
          for (let i = steps.length - 1; i >= 0; i--) {
            if (!steps[i].done) { steps[i] = { ...steps[i], done: true }; break; }
          }
          return { ...m, toolSteps: steps };
        });
      } else if (event === "text") {
        patchAssistant(asstId, (m) => ({ ...m, content: m.content + (data.delta || "") }));
      } else if (event === "done") {
        patchAssistant(asstId, (m) => ({
          ...m,
          content: data.answer ?? m.content,
          citations: data.citations || m.citations,
          toolSteps: (m.toolSteps || []).map((s) => ({ ...s, done: true })),
          streaming: false,
        }));
        if (sessionIdRef.current) upsert({ id: sessionIdRef.current, updatedAt: Date.now() });
      } else if (event === "error") {
        toast.error(data.message || "The agent failed");
      }
    };

    try {
      await api.chatStream(body, onEvent, controller.signal);
    } catch (e) {
      if (e.name !== "AbortError") {
        toast.error(e.message || "Request failed");
        patchAssistant(asstId, (m) => ({ ...m, content: m.content || "The request could not be completed.", streaming: false }));
      }
    } finally {
      patchAssistant(asstId, (m) => ({ ...m, streaming: false, toolSteps: (m.toolSteps || []).map((s) => ({ ...s, done: true })) }));
      setStreaming(false);
      abortRef.current = null;
      setTimeout(() => { if (ownSid && sessionIdRef.current === ownSid) saveTranscript(ownSid); }, 0);
    }
  };

  const stop = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  const toggleSource = (id) =>
    setSelectedSources((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  const activeTitle = sessions.find((s) => s.id === activeId)?.title;

  return (
    <AppShell
      title={activeTitle || "New conversation"}
      showDemo={api.demo}
      headerActions={messages.length > 0 && (
        <button type="button" data-testid="clear-chat-button" onClick={startNew} className="text-btn quiet min-h-[32px]">
          Clear
        </button>
      )}
      sidebarProps={{
        sessions,
        activeId,
        onSelect: selectSession,
        onNew: startNew,
        onDelete: (id) => { api.deleteSession(id).catch(() => {}); remove(id); if (id === activeId) startNew(); },
        onRename: rename,
        selectedSources,
        onToggleSource: toggleSource,
        onClearSources: () => setSelectedSources([]),
        onOpenSearch: () => setSearchOpen(true),
        theme,
        onToggleTheme,
      }}
      rightPanel={<SourceViewerPanel citation={sourceCitation} onClose={() => setSourceCitation(null)} />}
    >
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <EmptyState agentId={agentId} onPrompt={(p) => send(p)} onOpenSource={setSourceCitation} disabled={streaming} />
        ) : (
          <div className="mx-auto w-full max-w-[72ch] px-4 py-8 sm:px-6 md:px-8 space-y-9">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} onOpenSource={setSourceCitation} />
            ))}
          </div>
        )}
      </div>

        <Composer
          value={input}
          onChange={setInput}
          onSend={() => send()}
          onStop={stop}
          streaming={streaming}
          agentId={agentId}
          onAgentChange={setAgentId}
        />

      <LiteratureSearchModal
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        selectedSources={selectedSources}
        onOpenSource={setSourceCitation}
        onInsert={(text) => setInput((prev) => (prev ? prev + "\n\n" : "") + text)}
      />
    </AppShell>
  );
}
