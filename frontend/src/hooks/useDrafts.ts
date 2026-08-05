import { useState, useCallback } from "react";

export const useDraft = (conversationId: string | null) => {
  const key = conversationId ? `draft:${conversationId}` : "draft:new";

  const [draft, setDraftState] = useState<string>(() => {
    return localStorage.getItem(key) || "";
  });

  const setDraft = useCallback(
    (value: string) => {
      setDraftState(value);
      if (value) {
        localStorage.setItem(key, value);
      } else {
        localStorage.removeItem(key);
      }
    },
    [key]
  );

  const clearDraft = useCallback(() => {
    setDraftState("");
    localStorage.removeItem(key);
  }, [key]);

  return { draft, setDraft, clearDraft };
};
