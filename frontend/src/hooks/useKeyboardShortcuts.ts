import { useEffect } from "react";

export const useKeyboardShortcuts = (shortcuts: Record<string, () => void>) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const isInput =
        target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable;

      const key = e.key.toLowerCase();
      const ctrl = e.ctrlKey || e.metaKey;
      const shift = e.shiftKey;

      for (const [shortcut, callback] of Object.entries(shortcuts)) {
        const parts = shortcut.toLowerCase().split("+");
        const hasCtrl = parts.includes("ctrl");
        const hasShift = parts.includes("shift");
        const mainKey = parts[parts.length - 1];

        const ctrlMatch = hasCtrl === ctrl;
        const shiftMatch = hasShift === shift;
        const keyMatch = key === mainKey || (mainKey === "/" && e.key === "/");

        if (ctrlMatch && shiftMatch && keyMatch) {
          // Skip simple single character shortcuts when user is actively writing text
          if (isInput && !hasCtrl && key !== "escape") {
            continue;
          }

          e.preventDefault();
          callback();
          break;
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [shortcuts]);
};
