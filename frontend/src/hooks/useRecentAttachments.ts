import { useState, useEffect, useCallback } from "react";

interface RecentAttachment {
  name: string;
  size: number;
  type: string;
  lastUsed: number;
}

const STORAGE_KEY = "chat-recent-attachments";
const MAX_RECENT = 10;

export const useRecentAttachments = () => {
  const [recents, setRecents] = useState<RecentAttachment[]>([]);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          setRecents(parsed.sort((a, b) => b.lastUsed - a.lastUsed).slice(0, MAX_RECENT));
        }
      }
    } catch (e) {
      console.warn("Failed to load recent attachments:", e);
    }
  }, []);

  const addRecent = useCallback((file: File) => {
    const newRecent: RecentAttachment = {
      name: file.name,
      size: file.size,
      type: file.type,
      lastUsed: Date.now(),
    };

    setRecents((prev) => {
      const filtered = prev.filter((r) => r.name !== file.name || r.size !== file.size);
      const updated = [newRecent, ...filtered].slice(0, MAX_RECENT);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      } catch (e) {
        console.warn("Failed to save recent attachments:", e);
      }
      return updated;
    });
  }, []);

  const clearRecents = useCallback(() => {
    setRecents([]);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (e) {
      console.warn("Failed to clear recent attachments:", e);
    }
  }, []);

  return { recents, addRecent, clearRecents };
};

export default useRecentAttachments;