import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useRef,
  useMemo,
  ReactNode,
} from "react";
import { useUserSettings, useUpdateUserSettings } from "./useUserSettings";
import { FolderItem, TagItem } from "../api/userSettings";
import { useAuth } from "./useAuth";

export type Folder = FolderItem;
export type Tag = TagItem;

export interface ConversationMetadataContextType {
  pinnedIds: string[];
  folders: Folder[];
  tags: Record<string, Tag[]>;
  togglePin: (id: string) => void;
  createFolder: (name: string, description?: string, color?: string) => void;
  renameFolder: (id: string, name: string) => void;
  deleteFolder: (id: string) => void;
  moveConversationToFolder: (
    conversationId: string,
    folderId: string | null
  ) => void;
  addTag: (conversationId: string, tag: Tag) => void;
  removeTag: (conversationId: string, tagName: string) => void;
  syncStatus: "synced" | "saving" | "error";
  lastSyncedAt: Date | null;
  activeFilterTag: string | null;
  setActiveFilterTag: (tag: string | null) => void;
  activeFilterFolderId: string | null;
  setActiveFilterFolderId: (folderId: string | null) => void;
}

const ConversationMetadataContext =
  createContext<ConversationMetadataContextType | null>(null);

const DEFAULT_FOLDERS: Folder[] = [
  { id: "folder-general", name: "General", conversationIds: [] },
  { id: "folder-research", name: "Research", conversationIds: [] },
];

export const ConversationMetadataProvider: React.FC<{ children: ReactNode }> = ({
  children,
}) => {
  const { user } = useAuth();
  const { data: settingsData, isPending, isError } = useUserSettings();
  const updateSettingsMutation = useUpdateUserSettings();

  const [activeFilterTag, setActiveFilterTag] = useState<string | null>(null);
  const [activeFilterFolderId, setActiveFilterFolderId] = useState<
    string | null
  >(null);
  const hasMigratedLocalData = useRef(false);

  // 1. One-time auto-migration of legacy local storage on login
  useEffect(() => {
    if (!user?.id || hasMigratedLocalData.current || isPending || !settingsData) {
      return;
    }

    try {
      const legacyFolders = localStorage.getItem("conversation-folders");
      const legacyPins = localStorage.getItem("pinned-conversations");
      const legacyTags = localStorage.getItem("conversation-tags");

      const parsedFolders: Folder[] = legacyFolders ? JSON.parse(legacyFolders) : [];
      const parsedPins: string[] = legacyPins ? JSON.parse(legacyPins) : [];
      const parsedTags: Record<string, Tag[]> = legacyTags ? JSON.parse(legacyTags) : {};

      const hasLegacyData =
        parsedFolders.length > 0 ||
        parsedPins.length > 0 ||
        Object.keys(parsedTags).length > 0;

      const isCloudEmpty =
        (!settingsData.folders || settingsData.folders.length <= 2) &&
        (!settingsData.pinned_conversations ||
          settingsData.pinned_conversations.length === 0) &&
        (!settingsData.conversation_tags ||
          Object.keys(settingsData.conversation_tags).length === 0);

      if (hasLegacyData && isCloudEmpty) {
        // Merge & migrate to cloud
        updateSettingsMutation.mutate({
          folders: parsedFolders.length > 0 ? parsedFolders : settingsData.folders,
          pinned_conversations:
            parsedPins.length > 0
              ? parsedPins
              : settingsData.pinned_conversations,
          conversation_tags:
            Object.keys(parsedTags).length > 0
              ? parsedTags
              : settingsData.conversation_tags,
        });

        // Clean up legacy keys once migrated
        localStorage.removeItem("conversation-folders");
        localStorage.removeItem("pinned-conversations");
        localStorage.removeItem("conversation-tags");
      }
      hasMigratedLocalData.current = true;
    } catch (e) {
      console.warn("Auto-migration of local metadata skipped:", e);
      hasMigratedLocalData.current = true;
    }
  }, [user?.id, isPending, settingsData, updateSettingsMutation]);

  // Derived current values from settingsData with default fallbacks
  const folders = useMemo(() => {
    return settingsData?.folders && settingsData.folders.length > 0
      ? settingsData.folders
      : DEFAULT_FOLDERS;
  }, [settingsData?.folders]);

  const pinnedIds = useMemo(() => {
    return settingsData?.pinned_conversations ?? [];
  }, [settingsData?.pinned_conversations]);

  const tags = useMemo(() => {
    return settingsData?.conversation_tags ?? {};
  }, [settingsData?.conversation_tags]);

  const syncStatus: "synced" | "saving" | "error" =
    updateSettingsMutation.isPending
      ? "saving"
      : isError || updateSettingsMutation.isError
      ? "error"
      : "synced";

  const lastSyncedAt = useMemo(() => {
    return settingsData?.updated_at ? new Date(settingsData.updated_at) : null;
  }, [settingsData?.updated_at]);

  // Actions
  const togglePin = (id: string) => {
    const updated = pinnedIds.includes(id)
      ? pinnedIds.filter((pId) => pId !== id)
      : [...pinnedIds, id];
    updateSettingsMutation.mutate({ pinned_conversations: updated });
  };

  const createFolder = (name: string, description?: string, color?: string) => {
    const newFolder: Folder = {
      id: `folder-${Math.random().toString(36).substring(2, 9)}`,
      name,
      conversationIds: [],
      description,
      color,
    };
    const updated = [...folders, newFolder];
    updateSettingsMutation.mutate({ folders: updated });
  };

  const renameFolder = (id: string, name: string) => {
    const updated = folders.map((f) => (f.id === id ? { ...f, name } : f));
    updateSettingsMutation.mutate({ folders: updated });
  };

  const deleteFolder = (id: string) => {
    const updated = folders.filter((f) => f.id !== id);
    updateSettingsMutation.mutate({ folders: updated });
  };

  const moveConversationToFolder = (
    conversationId: string,
    folderId: string | null
  ) => {
    const updated = folders.map((f) => {
      const ids = f.conversationIds.filter((id) => id !== conversationId);
      if (f.id === folderId) {
        ids.push(conversationId);
      }
      return { ...f, conversationIds: ids };
    });
    updateSettingsMutation.mutate({ folders: updated });
  };

  const addTag = (conversationId: string, tag: Tag) => {
    const current = tags[conversationId] || [];
    if (current.some((t) => t.name.toLowerCase() === tag.name.toLowerCase())) {
      return;
    }
    const updated = {
      ...tags,
      [conversationId]: [...current, tag],
    };
    updateSettingsMutation.mutate({ conversation_tags: updated });
  };

  const removeTag = (conversationId: string, tagName: string) => {
    const current = tags[conversationId] || [];
    const updated = {
      ...tags,
      [conversationId]: current.filter(
        (t) => t.name.toLowerCase() !== tagName.toLowerCase()
      ),
    };
    updateSettingsMutation.mutate({ conversation_tags: updated });
  };

  return (
    <ConversationMetadataContext.Provider
      value={{
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
        syncStatus,
        lastSyncedAt,
        activeFilterTag,
        setActiveFilterTag,
        activeFilterFolderId,
        setActiveFilterFolderId,
      }}
    >
      {children}
    </ConversationMetadataContext.Provider>
  );
};

export const useLocalConversationMetadata = () => {
  const context = useContext(ConversationMetadataContext);
  if (!context) {
    throw new Error(
      "useLocalConversationMetadata must be used within a ConversationMetadataProvider"
    );
  }
  return context;
};
