import { useState } from "react";
import { Menu } from "lucide-react";
import { Sidebar } from "./Sidebar";

export const AppShell = ({
  title,
  sidebarProps,
  children,
  rightPanel,
  showDemo = false,
  headerActions,
}) => {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex h-dvh w-full min-w-0 overflow-hidden" style={{ background: "var(--paper)" }}>
      <Sidebar {...sidebarProps} mobileOpen={mobileOpen} onMobileOpenChange={setMobileOpen} />

      <main data-testid="main-chat-container" className="flex h-dvh min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-14 flex-shrink-0 items-center justify-between gap-3 border-b px-3 md:h-12 md:px-6" style={{ borderColor: "var(--rule)", paddingTop: "env(safe-area-inset-top)" }}>
          <div className="flex min-w-0 items-center gap-1.5">
            <button
              type="button"
              data-testid="mobile-nav-button"
              aria-label="Open navigation"
              onClick={() => setMobileOpen(true)}
              className="icon-btn !h-10 !w-10 md:!h-8 md:!w-8 md:hidden"
            >
              <Menu className="h-5 w-5" strokeWidth={1.75} />
            </button>
            <h2 className="min-w-0 truncate text-[14px] font-medium" style={{ color: "var(--ink)" }}>{title}</h2>
          </div>
          <div className="flex flex-shrink-0 items-center gap-2 sm:gap-4">
            {headerActions}
            {showDemo && (
              <span className="inline-flex items-center gap-1.5 text-[12px] sm:text-[12.5px]" style={{ color: "var(--revise)" }} title="No API URL configured — responses are simulated">
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--revise)" }} />
                Demo data
              </span>
            )}
          </div>
        </header>

        <div className="flex min-h-0 flex-1">
          <div className="flex min-w-0 flex-1 flex-col">{children}</div>
          {rightPanel}
        </div>
      </main>
    </div>
  );
};
