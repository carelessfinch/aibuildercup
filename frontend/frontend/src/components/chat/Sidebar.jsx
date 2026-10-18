import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { Plus, Trash2, Search, Library, Pencil, ChevronDown, Sun, Moon, FlaskConical, LogOut, MessageSquare } from "lucide-react";
import { useIndexedSources } from "@/hooks/useIndexedSources";
import { groupSessions } from "@/hooks/useChatSessions";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { useAuth } from "@/components/AuthProvider";
import { LOGOUT } from "@/constants/testIds";

// Hidden for the 225-source index; with nothing selected, answers and
// literature search use every source. Flip to re-enable.
const SHOW_SOURCE_FILTER = false;

const SourceFilter = ({ selected, onToggle, onClear }) => {
  const sources = useIndexedSources();
  return (
  <Popover>
    <PopoverTrigger asChild>
      <button type="button" data-testid="source-filter-dropdown" className="row-btn min-h-[40px]">
        <Library className="w-4 h-4" strokeWidth={1.75} style={{ color: "var(--ink-3)" }} />
        <span className="flex-1">Sources</span>
        <span className="text-[12px] tnum" style={{ color: selected.length ? "var(--accent)" : "var(--ink-3)" }}>
          {selected.length ? `${selected.length} of ${sources.length}` : `all ${sources.length}`}
        </span>
        <ChevronDown className="w-3.5 h-3.5" style={{ color: "var(--ink-4)" }} />
      </button>
    </PopoverTrigger>
    <PopoverContent align="start" sideOffset={6} collisionPadding={16} className="w-[min(340px,calc(100vw-2rem))] p-0 rounded-lg border" style={{ background: "var(--paper)", borderColor: "var(--rule-2)", boxShadow: "var(--shadow-lg)" }}>
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b" style={{ borderColor: "var(--rule)" }}>
        <p className="text-[13.5px] font-semibold" style={{ color: "var(--ink)" }}>Limit answers to</p>
        {selected.length > 0 && <button type="button" onClick={onClear} className="text-btn min-h-[32px]">Use all</button>}
      </div>
      <ul className="max-h-80 overflow-y-auto py-1.5 px-1.5">
        {sources.map((s) => {
          const checked = selected.includes(s.source_id);
          return (
            <li key={s.source_id}>
              <div
                role="checkbox"
                aria-checked={checked}
                tabIndex={0}
                data-testid={`source-filter-item-${s.source_id}`}
                onClick={() => onToggle(s.source_id)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onToggle(s.source_id); } }}
                className="row-btn min-h-[40px] items-start cursor-pointer"
                style={{ padding: "8px 10px" }}
              >
                <Checkbox checked={checked} tabIndex={-1} className="mt-[3px] pointer-events-none" />
                <span className="min-w-0">
                  <span className="block text-[13.5px] leading-snug break-words" style={{ color: "var(--ink)" }}>{s.title}</span>
                  <span className="block text-[12px] mt-0.5 tnum" style={{ color: "var(--ink-3)" }}>{s.authors} · {s.year}</span>
                </span>
              </div>
            </li>
          );
        })}
      </ul>
    </PopoverContent>
  </Popover>
  );
};

const SidebarContent = ({
  sessions = [], activeId, onSelect, onNew, onDelete, onRename,
  selectedSources = [], onToggleSource, onClearSources, onOpenSearch,
  theme, onToggleTheme, onNavigate, noSessionFeatures,
}) => {
  const { user, logout } = useAuth();
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState("");
  const grouped = groupSessions(sessions);
  const location = useLocation();

  const commitRename = (id) => {
    if (draft.trim()) onRename?.(id, draft.trim());
    setEditing(null);
  };

  const navigate = (fn) => () => {
    fn?.();
    onNavigate?.();
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 px-4 pt-5 pb-3">
        <p className="font-serif-read font-semibold text-[17px] tracking-[-0.01em] px-2 truncate" style={{ color: "var(--ink)" }}>Plasma Research</p>
      </div>

      <nav className="px-2.5 space-y-0.5">
        <NavLink
          to="/"
          data-testid="new-chat-button"
          onClick={navigate(onNew)}
          className="row-btn min-h-[40px]"
          style={{ color: "var(--ink)", background: location.pathname === "/" ? "var(--paper-3)" : undefined }}
        >
          <span className="inline-flex w-4 h-4 items-center justify-center rounded-full" style={{ background: "var(--accent)" }}>
            <Plus className="w-3 h-3" strokeWidth={2.5} style={{ color: "var(--paper)" }} />
          </span>
          New chat
        </NavLink>
        <NavLink
          to="/validate"
          data-testid="validate-simulation-link"
          onClick={navigate()}
          className="row-btn min-h-[40px]"
          style={{ color: "var(--ink)", background: location.pathname === "/validate" ? "var(--paper-3)" : undefined }}
        >
          <FlaskConical className="w-4 h-4" strokeWidth={1.75} style={{ color: "var(--ink-3)" }} />
          Validate simulation
        </NavLink>

        {!noSessionFeatures && (
          <>
            <button type="button" data-testid="literature-search-trigger" onClick={navigate(onOpenSearch)} className="row-btn min-h-[40px]">
              <Search className="w-4 h-4" strokeWidth={1.75} style={{ color: "var(--ink-3)" }} />
              Search literature
            </button>
            {SHOW_SOURCE_FILTER && (
              <SourceFilter selected={selectedSources} onToggle={onToggleSource} onClear={onClearSources} />
            )}
          </>
        )}
      </nav>

      {!noSessionFeatures && (
        <div data-testid="chat-history-list" className="flex-1 overflow-y-auto px-2.5 mt-5 pb-4">
          {sessions.length === 0 && (
            <p className="px-3 pt-2 text-[13px] leading-relaxed" style={{ color: "var(--ink-3)" }}>
              Your conversations will be listed here. They stay in this browser.
            </p>
          )}
          {grouped.map(([label, items]) => (
            <section key={label} className="mb-5">
              <h2 className="px-3 mb-1 text-[12px] font-semibold" style={{ color: "var(--ink-3)" }}>{label}</h2>
              <ul className="space-y-px">
                {items.map((s) => {
                  const isActive = s.id === activeId;
                  return (
                    <li
                      key={s.id}
                      data-testid={`chat-session-item-${s.id}`}
                      data-active={isActive}
                      onClick={() => editing !== s.id && onSelect?.(s.id)}
                      className="row-btn group min-h-[40px] cursor-pointer"
                      style={{ padding: "6px 10px", fontWeight: isActive ? 500 : 400, color: isActive ? "var(--ink)" : "var(--ink-2)" }}
                    >
                      {editing === s.id ? (
                        <input
                          autoFocus
                          aria-label="Rename conversation"
                          value={draft}
                          onChange={(e) => setDraft(e.target.value)}
                          onBlur={() => commitRename(s.id)}
                          onKeyDown={(e) => { if (e.key === "Enter") commitRename(s.id); if (e.key === "Escape") setEditing(null); }}
                          className="h-8 flex-1 min-w-0 bg-transparent text-[13.5px] border-b focus:outline-none"
                          style={{ color: "var(--ink)", borderColor: "var(--accent)" }}
                        />
                      ) : (
                        <span className="flex min-w-0 flex-1 items-center gap-2">
                          <MessageSquare className="w-3.5 h-3.5 flex-shrink-0" style={{ color: "var(--ink-4)" }} />
                          <span className="truncate text-[13.5px]">{s.title}</span>
                        </span>
                      )}
                      {editing !== s.id && (
                        <span className="flex flex-shrink-0 items-center -mr-1">
                          <button
                            type="button"
                            aria-label="Rename"
                            onClick={(e) => { e.stopPropagation(); setEditing(s.id); setDraft(s.title); }}
                            className="icon-btn !h-10 !w-10 md:!h-7 md:!w-7"
                          >
                            <Pencil className="w-3.5 h-3.5" strokeWidth={1.75} />
                          </button>
                          <button
                            type="button"
                            aria-label="Delete"
                            data-testid={`delete-chat-session-${s.id}`}
                            onClick={(e) => { e.stopPropagation(); onDelete?.(s.id); }}
                            className="icon-btn !h-10 !w-10 md:!h-7 md:!w-7 hover:!text-[var(--escalate)]"
                          >
                            <Trash2 className="w-3.5 h-3.5" strokeWidth={1.75} />
                          </button>
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}

      <div className="mt-auto px-2.5 py-3 border-t" style={{ borderColor: "var(--rule)" }}>
        <button type="button" data-testid="theme-toggle" onClick={onToggleTheme} aria-pressed={theme === "dark"} className="row-btn min-h-[40px]">
          {theme === "dark" ? <Sun className="w-4 h-4" strokeWidth={1.75} style={{ color: "var(--ink-3)" }} /> : <Moon className="w-4 h-4" strokeWidth={1.75} style={{ color: "var(--ink-3)" }} />}
          <span className="flex-1">{theme === "dark" ? "Light mode" : "Dark mode"}</span>
          <span className="relative inline-block w-7 h-4 rounded-full flex-shrink-0" style={{ background: theme === "dark" ? "var(--accent)" : "var(--rule-2)", transition: "background-color 180ms var(--ease-out)" }}>
            <span className="absolute top-0.5 w-3 h-3 rounded-full" style={{ background: "var(--paper)", left: theme === "dark" ? 14 : 2, transition: "left 180ms var(--ease-out)" }} />
          </span>
        </button>
        <div className="mt-1 flex min-h-[40px] items-center gap-2 rounded-md px-2.5">
          <span aria-hidden="true" className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-[11px] font-bold uppercase" style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>
            {(user?.username || "U").slice(0, 1)}
          </span>
          <span data-testid="sidebar-username" className="min-w-0 flex-1 truncate text-[13px]" style={{ color: "var(--ink)" }}>{user?.username || "Signed in"}</span>
          <button type="button" data-testid={LOGOUT.button} onClick={logout} className="inline-flex h-9 items-center gap-1.5 rounded-md px-2 text-[12.5px] font-medium hover:bg-[var(--paper-3)]" style={{ color: "var(--ink-2)" }}>
            <LogOut className="h-3.5 w-3.5" strokeWidth={1.75} />Log out
          </button>
        </div>
      </div>
    </div>
  );
};

export function Sidebar(props) {
  const [aboveMd, setAboveMd] = useState(() => window.matchMedia("(min-width: 768px)").matches);
  useEffect(() => {
    const query = window.matchMedia("(min-width: 768px)");
    const changed = () => setAboveMd(query.matches);
    query.addEventListener("change", changed);
    return () => query.removeEventListener("change", changed);
  }, []);

  return (
    <>
      {aboveMd && (
        <aside
          data-testid="left-sidebar"
          className="flex w-[272px] flex-shrink-0 flex-col border-r h-dvh"
          style={{ background: "var(--paper-2)", borderColor: "var(--rule)" }}
        >
          <SidebarContent {...props} />
        </aside>
      )}
      {!aboveMd && (
        <Sheet open={Boolean(props.mobileOpen)} onOpenChange={props.onMobileOpenChange}>
          <SheetContent
            side="left"
            aria-describedby={undefined}
            className="w-[min(320px,calc(100vw-56px))] border-r p-0"
            style={{ background: "var(--paper-2)", borderColor: "var(--rule)" }}
          >
        <SheetTitle className="sr-only">Application navigation</SheetTitle>
            <SidebarContent {...props} onNavigate={() => props.onMobileOpenChange?.(false)} />
          </SheetContent>
        </Sheet>
      )}
    </>
  );
}
