import React, { useMemo, useState, useEffect } from "react";
import { Pin } from "lucide-react";
import { Conversation } from "../../types";
import { ConversationItem } from "../sidebar/ConversationItem";
import { Folder, Tag } from "../../hooks/useLocalConversationMetadata";
import { isToday, isYesterday, subDays, isAfter } from "date-fns";
import { SidebarFolders } from "./SidebarFolders";

interface SidebarConversationListProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => Promise<unknown>;
  onDelete: (id: string) => Promise<unknown>;
  searchQuery: string;

  // Local metadata props
  pinnedIds: string[];
  folders: Folder[];
  tags: Record<string, Tag[]>;
  togglePin: (id: string) => void;
  createFolder: (name: string) => void;
  renameFolder: (id: string, name: string) => void;
  deleteFolder: (id: string) => void;
  moveConversationToFolder: (conversationId: string, folderId: string | null) => void;
  addTag: (conversationId: string, tag: Tag) => void;
  removeTag: (conversationId: string, name: string) => void;
}

export const SidebarConversationList: React.FC<SidebarConversationListProps> = ({
  conversations,
  activeId,
  onSelect,
  onRename,
  onDelete,
  searchQuery,
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
}) => {
  const [expandedFolders] = useState<Record<string, boolean>>(() => ({
    "folder-general": true,
    "folder-research": true,
  }));
  const [keyboardSelectIdx, setKeyboardSelectIdx] = useState<number>(-1);

  const conversationMap = useMemo(() => {
    return new Map(conversations.map((c) => [c.id, c]));
  }, [conversations]);

  const filteredConversations = useMemo(() => {
    if (!searchQuery.trim()) return conversations;
    const lower = searchQuery.toLowerCase();
    return conversations.filter((c) => c.title.toLowerCase().includes(lower));
  }, [conversations, searchQuery]);

  const folderConversations = useMemo(() => {
    const map: Record<string, Conversation[]> = {};
    folders.forEach((f) => {
      map[f.id] = f.conversationIds
        .map((id) => conversationMap.get(id))
        .filter((c): c is Conversation => !!c && (!searchQuery.trim() || c.title.toLowerCase().includes(searchQuery.toLowerCase())));
    });
    return map;
  }, [folders, conversationMap, searchQuery]);

  const folderedConversationIds = useMemo(() => {
    const set = new Set<string>();
    folders.forEach((f) => {
      f.conversationIds.forEach((id) => set.add(id));
    });
    return set;
  }, [folders]);

  const pinnedConversations = useMemo(() => {
    return pinnedIds
      .map((id) => conversationMap.get(id))
      .filter((c): c is Conversation => !!c && (!searchQuery.trim() || c.title.toLowerCase().includes(searchQuery.toLowerCase())));
  }, [pinnedIds, conversationMap, searchQuery]);

  const unfolderedConversations = useMemo(() => {
    return filteredConversations.filter((c) => !folderedConversationIds.has(c.id));
  }, [filteredConversations, folderedConversationIds]);

  const unfolderedGroups = useMemo(() => {
    const today: Conversation[] = [];
    const yesterday: Conversation[] = [];
    const last7Days: Conversation[] = [];
    const older: Conversation[] = [];

    const now = new Date();
    const sevenDaysAgo = subDays(now, 7);

    unfolderedConversations.forEach((c) => {
      const date = new Date(c.updated_at || c.last_message_at || c.created_at);
      if (isToday(date)) {
        today.push(c);
      } else if (isYesterday(date)) {
        yesterday.push(c);
      } else if (isAfter(date, sevenDaysAgo)) {
        last7Days.push(c);
      } else {
        older.push(c);
      }
    });

    return { today, yesterday, last7Days, older };
  }, [unfolderedConversations]);

  const flatVisibleConversations = useMemo(() => {
    const list: Conversation[] = [];
    pinnedConversations.forEach((c) => list.push(c));
    folders.forEach((folder) => {
      if (expandedFolders[folder.id]) {
        const nested = folderConversations[folder.id] || [];
        nested.forEach((c) => list.push(c));
      }
    });
    const { today, yesterday, last7Days, older } = unfolderedGroups;
    [...today, ...yesterday, ...last7Days, ...older].forEach((c) => {
      if (!list.some((existing) => existing.id === c.id)) {
        list.push(c);
      }
    });
    return list;
  }, [pinnedConversations, folders, folderConversations, expandedFolders, unfolderedGroups]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      ) {
        return;
      }
      if (flatVisibleConversations.length === 0) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setKeyboardSelectIdx((prev) =>
          prev < flatVisibleConversations.length - 1 ? prev + 1 : 0
        );
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setKeyboardSelectIdx((prev) =>
          prev > 0 ? prev - 1 : flatVisibleConversations.length - 1
        );
      } else if (e.key === "Enter" && keyboardSelectIdx >= 0) {
        e.preventDefault();
        const selected = flatVisibleConversations[keyboardSelectIdx];
        if (selected) onSelect(selected.id);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [flatVisibleConversations, keyboardSelectIdx, onSelect]);

  useEffect(() => {
    if (activeId) {
      const idx = flatVisibleConversations.findIndex((c) => c.id === activeId);
      if (idx !== -1) {
        setKeyboardSelectIdx(idx);
      }
    }
  }, [activeId, flatVisibleConversations]);

  return (
    <div
      style={{
        flex: 1,
        width: "100%",
        overflowY: "auto",
        padding: "12px 10px",
        display: "flex",
        flexDirection: "column",
        gap: "16px",
        scrollbarWidth: "thin",
      }}
    >
      {pinnedConversations.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
          <div
            style={{
              padding: "2px 4px 4px",
              fontSize: "11px",
              fontWeight: 600,
              color: "#f59e0b",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              display: "flex",
              alignItems: "center",
              gap: "5px",
            }}
          >
            <Pin size={10} style={{ fill: "currentColor" }} />
            <span>Pinned</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "1px" }}>
            {pinnedConversations.map((c, index) => (
              <ConversationItem
                key={`pinned-${c.id}`}
                conversation={c}
                isActive={c.id === activeId}
                onSelect={() => onSelect(c.id)}
                onRename={onRename}
                onDelete={onDelete}
                isPinned={true}
                onTogglePin={() => togglePin(c.id)}
                folders={folders}
                onMoveToFolder={(fId) => moveConversationToFolder(c.id, fId)}
                tags={tags[c.id] || []}
                onAddTag={(tag) => addTag(c.id, tag)}
                onRemoveTag={(tName) => removeTag(c.id, tName)}
                isHighlighted={keyboardSelectIdx === index}
              />
            ))}
          </div>
        </div>
      )}

      {/* Folders Section */}
      <SidebarFolders
        folders={folders}
        folderConversations={folderConversations}
        activeId={activeId}
        onSelect={onSelect}
        onRename={onRename}
        onDelete={onDelete}
        pinnedIds={pinnedIds}
        tags={tags}
        togglePin={togglePin}
        createFolder={createFolder}
        renameFolder={renameFolder}
        deleteFolder={deleteFolder}
        moveConversationToFolder={moveConversationToFolder}
        addTag={addTag}
        removeTag={removeTag}
        keyboardSelectIdx={keyboardSelectIdx}
        flatVisibleConversations={flatVisibleConversations}
      />

      {/* Date-grouped Un-foldered Category */}
      <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
        {Object.entries(unfolderedGroups).map(([groupKey, groupDocs]) => {
          if (groupDocs.length === 0) return null;

          const groupLabels: Record<string, string> = {
            today: "Today",
            yesterday: "Yesterday",
            last7Days: "Previous 7 Days",
            older: "Older",
          };

          return (
            <div key={groupKey} style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
              <div
                style={{
                  padding: "2px 4px 4px",
                  fontSize: "11px",
                  fontWeight: 600,
                  color: "var(--text-muted, #737373)",
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                }}
              >
                {groupLabels[groupKey]}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "1px" }}>
                {groupDocs.map((c) => {
                  const globalIndex = flatVisibleConversations.findIndex((vis) => vis.id === c.id);
                  return (
                    <ConversationItem
                      key={`unfoldered-${c.id}`}
                      conversation={c}
                      isActive={c.id === activeId}
                      onSelect={() => onSelect(c.id)}
                      onRename={onRename}
                      onDelete={onDelete}
                      isPinned={pinnedIds.includes(c.id)}
                      onTogglePin={() => togglePin(c.id)}
                      folders={folders}
                      onMoveToFolder={(fId) => moveConversationToFolder(c.id, fId)}
                      tags={tags[c.id] || []}
                      onAddTag={(tag) => addTag(c.id, tag)}
                      onRemoveTag={(tName) => removeTag(c.id, tName)}
                      isHighlighted={keyboardSelectIdx === globalIndex}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
