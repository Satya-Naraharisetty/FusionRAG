import React, { useMemo, useState, useEffect } from "react";
import { Pin } from "lucide-react";
import { Conversation } from "../../types";
import { ConversationItem } from "../sidebar/ConversationItem";
import { Folder, Tag } from "../../hooks/useLocalConversationMetadata";
import { isToday, isYesterday, subDays, isAfter } from "../../lib/utils";
import { SidebarFolders } from "./SidebarFolders";

interface SidebarConversationListProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => Promise<unknown>;
  onDelete: (id: string) => Promise<unknown>;
  searchQuery: string;
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

const GROUP_LABELS: Record<string, string> = {
  today:    "Today",
  yesterday:"Yesterday",
  last7Days:"Previous 7 Days",
  older:    "Older",
};

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
  const [expandedFolders] = useState<Record<string, boolean>>({
    "folder-general":  true,
    "folder-research": true,
  });
  const [keyboardSelectIdx, setKeyboardSelectIdx] = useState(-1);

  const conversationMap = useMemo(
    () => new Map(conversations.map((c) => [c.id, c])),
    [conversations]
  );

  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return conversations;
    const q = searchQuery.toLowerCase();
    return conversations.filter((c) => c.title.toLowerCase().includes(q));
  }, [conversations, searchQuery]);

  const folderConversations = useMemo(() => {
    const map: Record<string, Conversation[]> = {};
    folders.forEach((f) => {
      map[f.id] = f.conversationIds
        .map((id) => conversationMap.get(id))
        .filter((c): c is Conversation =>
          !!c && (!searchQuery.trim() || c.title.toLowerCase().includes(searchQuery.toLowerCase()))
        );
    });
    return map;
  }, [folders, conversationMap, searchQuery]);

  const folderedIds = useMemo(() => {
    const set = new Set<string>();
    folders.forEach((f) => f.conversationIds.forEach((id) => set.add(id)));
    return set;
  }, [folders]);

  const pinned = useMemo(() =>
    pinnedIds
      .map((id) => conversationMap.get(id))
      .filter((c): c is Conversation =>
        !!c && (!searchQuery.trim() || c.title.toLowerCase().includes(searchQuery.toLowerCase()))
      ),
    [pinnedIds, conversationMap, searchQuery]
  );

  const unfoldered = useMemo(
    () => filtered.filter((c) => !folderedIds.has(c.id)),
    [filtered, folderedIds]
  );

  const groups = useMemo(() => {
    const today: Conversation[]    = [];
    const yesterday: Conversation[]= [];
    const last7Days: Conversation[]= [];
    const older: Conversation[]    = [];
    const sevenAgo = subDays(new Date(), 7);

    unfoldered.forEach((c) => {
      const d = new Date(c.updated_at || c.last_message_at || c.created_at);
      if      (isToday(d))           today.push(c);
      else if (isYesterday(d))       yesterday.push(c);
      else if (isAfter(d, sevenAgo)) last7Days.push(c);
      else                           older.push(c);
    });
    return { today, yesterday, last7Days, older };
  }, [unfoldered]);

  const flatVisible = useMemo(() => {
    const list: Conversation[] = [];
    pinned.forEach((c) => list.push(c));
    folders.forEach((folder) => {
      if (expandedFolders[folder.id]) {
        (folderConversations[folder.id] || []).forEach((c) => list.push(c));
      }
    });
    const { today, yesterday, last7Days, older } = groups;
    [...today, ...yesterday, ...last7Days, ...older].forEach((c) => {
      if (!list.some((e) => e.id === c.id)) list.push(c);
    });
    return list;
  }, [pinned, folders, folderConversations, expandedFolders, groups]);

  // Keyboard navigation
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) return;
      if (flatVisible.length === 0) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setKeyboardSelectIdx((p) => (p < flatVisible.length - 1 ? p + 1 : 0));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setKeyboardSelectIdx((p) => (p > 0 ? p - 1 : flatVisible.length - 1));
      } else if (e.key === "Enter" && keyboardSelectIdx >= 0) {
        e.preventDefault();
        const sel = flatVisible[keyboardSelectIdx];
        if (sel) onSelect(sel.id);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [flatVisible, keyboardSelectIdx, onSelect]);

  useEffect(() => {
    if (activeId) {
      const idx = flatVisible.findIndex((c) => c.id === activeId);
      if (idx !== -1) setKeyboardSelectIdx(idx);
    }
  }, [activeId, flatVisible]);

  return (
    <div className="flex-1 overflow-y-auto px-2.5 py-3 flex flex-col gap-4 scrollbar-thin">

      {/* Pinned */}
      {pinned.length > 0 && (
        <div className="flex flex-col gap-0.5">
          <div className="flex items-center gap-1.5 px-1 pb-1 text-[10px] font-semibold text-amber-500 uppercase tracking-wider">
            <Pin size={9} className="fill-current flex-shrink-0" />
            <span>Pinned</span>
          </div>
          {pinned.map((c, i) => (
            <ConversationItem
              key={`pinned-${c.id}`}
              conversation={c}
              isActive={c.id === activeId}
              onSelect={() => onSelect(c.id)}
              onRename={onRename}
              onDelete={onDelete}
              isPinned
              onTogglePin={() => togglePin(c.id)}
              folders={folders}
              onMoveToFolder={(fId) => moveConversationToFolder(c.id, fId)}
              tags={tags[c.id] || []}
              onAddTag={(tag) => addTag(c.id, tag)}
              onRemoveTag={(n) => removeTag(c.id, n)}
              isHighlighted={keyboardSelectIdx === i}
            />
          ))}
        </div>
      )}

      {/* Folders */}
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
        flatVisibleConversations={flatVisible}
      />

      {/* Date-grouped conversations */}
      <div className="flex flex-col gap-4">
        {(["today", "yesterday", "last7Days", "older"] as const).map((key) => {
          const group = groups[key];
          if (group.length === 0) return null;
          return (
            <div key={key} className="flex flex-col gap-0.5">
              <div className="px-1 pb-1 text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                {GROUP_LABELS[key]}
              </div>
              {group.map((c) => {
                const globalIdx = flatVisible.findIndex((v) => v.id === c.id);
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
                    onRemoveTag={(n) => removeTag(c.id, n)}
                    isHighlighted={keyboardSelectIdx === globalIdx}
                  />
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
};
