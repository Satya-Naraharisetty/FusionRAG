import { useState, useEffect } from "react";

export interface Folder {
  id: string;
  name: string;
  conversationIds: string[];
}

export interface Tag {
  name: string;
  color: string; // e.g., "red", "blue", "emerald"
}

export const useLocalConversationMetadata = () => {
  const [pinnedIds, setPinnedIds] = useState<string[]>(() => {
    const saved = localStorage.getItem("pinned-conversations");
    return saved ? JSON.parse(saved) : [];
  });

  const [folders, setFolders] = useState<Folder[]>(() => {
    const saved = localStorage.getItem("conversation-folders");
    return saved ? JSON.parse(saved) : [
      { id: "folder-general", name: "General", conversationIds: [] },
      { id: "folder-research", name: "Research", conversationIds: [] },
    ];
  });

  const [tags, setTags] = useState<Record<string, Tag[]>>(() => {
    const saved = localStorage.getItem("conversation-tags");
    return saved ? JSON.parse(saved) : {};
  });

  useEffect(() => {
    localStorage.setItem("pinned-conversations", JSON.stringify(pinnedIds));
  }, [pinnedIds]);

  useEffect(() => {
    localStorage.setItem("conversation-folders", JSON.stringify(folders));
  }, [folders]);

  useEffect(() => {
    localStorage.setItem("conversation-tags", JSON.stringify(tags));
  }, [tags]);

  const togglePin = (id: string) => {
    setPinnedIds((prev) =>
      prev.includes(id) ? prev.filter((pId) => pId !== id) : [...prev, id]
    );
  };

  const createFolder = (name: string) => {
    const newFolder: Folder = {
      id: `folder-${Math.random().toString(36).substring(2, 9)}`,
      name,
      conversationIds: [],
    };
    setFolders((prev) => [...prev, newFolder]);
  };

  const renameFolder = (id: string, name: string) => {
    setFolders((prev) =>
      prev.map((f) => (f.id === id ? { ...f, name } : f))
    );
  };

  const deleteFolder = (id: string) => {
    setFolders((prev) => prev.filter((f) => f.id !== id));
  };

  const moveConversationToFolder = (conversationId: string, folderId: string | null) => {
    setFolders((prev) =>
      prev.map((f) => {
        // Remove from existing folders
        let ids = f.conversationIds.filter((id) => id !== conversationId);
        // Add to target folder if it matches
        if (f.id === folderId) {
          ids = [...ids, conversationId];
        }
        return { ...f, conversationIds: ids };
      })
    );
  };

  const addTag = (conversationId: string, tag: Tag) => {
    setTags((prev) => {
      const current = prev[conversationId] || [];
      if (current.some((t) => t.name.toLowerCase() === tag.name.toLowerCase())) {
        return prev;
      }
      return {
        ...prev,
        [conversationId]: [...current, tag],
      };
    });
  };

  const removeTag = (conversationId: string, tagName: string) => {
    setTags((prev) => {
      const current = prev[conversationId] || [];
      return {
        ...prev,
        [conversationId]: current.filter((t) => t.name.toLowerCase() !== tagName.toLowerCase()),
      };
    });
  };

  return {
    pinnedIds,
    folders,
    tags,
    togglePin,
    createFolder,
    renameFolder,
    deleteFolder,
    moveConversationToFolder,
    addTag,
    removeTag,
  };
};
