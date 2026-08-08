import React, { useState, useEffect } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { MobileDrawer } from "./MobileDrawer";
import { OfflineBanner } from "./OfflineBanner";
import { useSidebarState } from "../../hooks/useSidebarState";
import { useKeyboardShortcuts } from "../../hooks/useKeyboardShortcuts";
import { CommandPalette } from "../command/CommandPalette";
import { OnboardingTour } from "./OnboardingTour";

export const ChatLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  useSidebarState();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

  // Focus main-content on page navigation for screen readers
  useEffect(() => {
    const mainEl = document.getElementById("main-content");
    if (mainEl) {
      mainEl.focus();
    }
  }, [location.pathname]);

  // Register global shortcuts
  useKeyboardShortcuts({
    "ctrl+n": () => {
      navigate("/chat");
    },
    "ctrl+/": () => {
      const searchInput = document.getElementById("sidebar-search-input");
      if (searchInput) searchInput.focus();
    },
    "ctrl+k": () => {
      setCommandPaletteOpen((prev) => !prev);
    },
    "ctrl+shift+o": () => {
      navigate("/documents");
    },
    "ctrl+shift+s": () => {
      navigate("/settings");
    },
    "escape": () => {
      setCommandPaletteOpen(false);
      setMobileOpen(false);
    },
  });

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden font-sans bg-[var(--bg-primary)] text-[var(--text-primary)]">
      {/* Skip to main content */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:px-4 focus:py-2 focus:bg-[var(--bg-elevated)] focus:text-[var(--text-primary)] focus:rounded-[var(--radius-md)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/50 text-xs font-semibold"
      >
        Skip to main content
      </a>

      {/* Offline Banner if disconnected */}
      <OfflineBanner />

      <div className="flex flex-1 w-full overflow-hidden relative">
        {/* Desktop Sidebar */}
        <Sidebar className="hidden md:flex flex-shrink-0" />

        {/* Mobile Header Bar */}
        <div className="md:hidden absolute top-3 left-3 z-30 flex items-center gap-2">
          <MobileDrawer open={mobileOpen} onOpenChange={setMobileOpen} />
        </div>

        {/* Main Content Pane */}
        <main
          id="main-content"
          tabIndex={-1}
          className="flex-1 flex flex-col min-w-0 h-full overflow-hidden relative focus:outline-none bg-[var(--bg-primary)]"
        >
          <Outlet />
        </main>
      </div>

      {/* Global Command Palette */}
      <CommandPalette open={commandPaletteOpen} onOpenChange={setCommandPaletteOpen} />

      {/* Onboarding Tour overlay */}
      <OnboardingTour />
    </div>
  );
};
export default ChatLayout;
