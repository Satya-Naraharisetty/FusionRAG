import { useState, useEffect } from "react";

interface SidebarState {
  collapsed: boolean;
  width: number;
  lastConversationId: string | null;
}

export const useSidebarState = () => {
  const [state, setState] = useState<SidebarState>(() => {
    const saved = localStorage.getItem("sidebar");
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch (_e) {
        // use default
      }
    }
    return {
      collapsed: false,
      width: 260,
      lastConversationId: null,
    };
  });

  const setCollapsed = (collapsed: boolean) => {
    setState((prev) => ({ ...prev, collapsed }));
  };

  const setWidth = (width: number) => {
    setState((prev) => ({ ...prev, width }));
  };

  const setLastConversationId = (id: string | null) => {
    setState((prev) => ({ ...prev, lastConversationId: id }));
  };

  useEffect(() => {
    localStorage.setItem("sidebar", JSON.stringify(state));
  }, [state]);

  return {
    collapsed: state.collapsed,
    width: state.width,
    lastConversationId: state.lastConversationId,
    setCollapsed,
    setWidth,
    setLastConversationId,
  };
};
