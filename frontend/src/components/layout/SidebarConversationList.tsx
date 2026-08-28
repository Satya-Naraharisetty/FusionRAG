import React, { useMemo, useState, useEffect } from "react";
import { Conversation } from "../../types";
import { ConversationItem } from "../sidebar/ConversationItem";
import { Folder, Tag, useLocalConversationMetadata } from "../../hooks/useLocalConversationMetadata";
import { useLocale } from "../../lib/messages";
import { X, Tag as TagIcon } from "lucide-react";

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
  moveConversationToFolder,
  addTag,
  removeTag,
}) => {
  const { t } = useLocale();
  const { activeFilterTag, setActiveFilterTag } = useLocalConversationMetadata();
  const [keyboardSelectIdx, setKeyboardSelectIdx] = useState<number>(-1);

  const conversationMap = useMemo(
    () => new Map(conversations.map((c) => [c.id, c])),
    [conversations]
  );

  // Collect unique applied tags
  const appliedTags = useMemo(() => {
    const map = new Map<string, string>();
    Object.values(tags).forEach((tagList) => {
      tagList.forEach((t) => map.set(t.name.toLowerCase(), t.color));
    });
    return Array.from(map.entries()).map(([name, color]) => ({ name, color }));
  }, [tags]);

  const filtered = useMemo(() => {
    let result = conversations;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter((c) => c.title.toLowerCase().includes(q));
    }
    if (activeFilterTag) {
      result = result.filter((c) =>
        tags[c.id]?.some((t) => t.name.toLowerCase() === activeFilterTag.toLowerCase())
      );
    }
    return result;
  }, [conversations, searchQuery, activeFilterTag, tags]);

  const sortedConversations = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const timeA = new Date(a.updated_at || a.last_message_at || a.created_at).getTime();
      const timeB = new Date(b.updated_at || b.last_message_at || b.created_at).getTime();
      return timeB - timeA;
    });
  }, [filtered]);

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

  const recents = useMemo(() => {
    // Show only un-pinned AND un-foldered conversations sorted by latest activity descending
    return sortedConversations.filter(
      (c) => !pinnedIds.includes(c.id) && !folderedIds.has(c.id)
    );
  }, [sortedConversations, pinnedIds, folderedIds]);

  const flatVisible = useMemo(() => {
    return [...pinned, ...recents];
  }, [pinned, recents]);

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
      setKeyboardSelectIdx(idx);
    } else {
      setKeyboardSelectIdx(-1);
    }
  }, [activeId, flatVisible]);

  return (
    <div className="flex-1 overflow-y-auto px-2 py-2 flex flex-col gap-3 scrollbar-thin">
      {/* ── Active Tag Filter Pill / Tags Bar ── */}
      {appliedTags.length > 0 && (
        <div className="flex items-center gap-1 overflow-x-auto scrollbar-none pb-0.5 px-1">
          <TagIcon size={11} className="text-[var(--text-muted)] flex-shrink-0" />
          {appliedTags.map((t) => {
            const isSelected = activeFilterTag?.toLowerCase() === t.name.toLowerCase();
            return (
              <button
                key={t.name}
                onClick={() => setActiveFilterTag(isSelected ? null : t.name)}
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium transition-colors cursor-pointer flex-shrink-0 ${
                  isSelected
                    ? "bg-[var(--accent-primary)] text-zinc-950 font-semibold"
                    : "bg-[var(--bg-tertiary)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)]"
                }`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${t.color}`} />
                <span>{t.name}</span>
                {isSelected && <X size={10} />}
              </button>
            );
          })}
        </div>
      )}

      {/* ── Pinned Section ── */}
      {pinned.length > 0 && (
        <div className="flex flex-col gap-0.5">
          <div className="flex items-center gap-1.5 px-2 pb-1 text-[11px] font-medium text-[var(--text-muted)] tracking-tight">
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
              currentFolderId={folders.find((f) => f.conversationIds.includes(c.id))?.id}
              tags={tags[c.id] || []}
              onAddTag={(tag) => addTag(c.id, tag)}
              onRemoveTag={(n) => removeTag(c.id, n)}
              isHighlighted={keyboardSelectIdx === i}
            />
          ))}
        </div>
      )}

      {/* ── Recents Section (Latest on top) ── */}
      <div className="flex flex-col gap-0.5">
        <div className="flex items-center justify-between px-2 pb-1 text-[11px] font-medium text-[var(--text-muted)] tracking-tight">
          <span>Recents</span>
          {recents.length > 0 && (
            <span className="text-[10px] text-[var(--text-muted)] opacity-60 font-mono">
              {recents.length}
            </span>
          )}
        </div>
        {recents.length === 0 && pinned.length === 0 ? (
          <p className="py-4 px-2 text-xs text-[var(--text-muted)] text-center italic">
            {searchQuery ? "No matching conversations" : t("nav.noConversations")}
          </p>
        ) : (
          recents.map((c) => {
            const globalIdx = flatVisible.findIndex((v) => v.id === c.id);
            return (
              <ConversationItem
                key={`recent-${c.id}`}
                conversation={c}
                isActive={c.id === activeId}
                onSelect={() => onSelect(c.id)}
                onRename={onRename}
                onDelete={onDelete}
                isPinned={pinnedIds.includes(c.id)}
                onTogglePin={() => togglePin(c.id)}
                folders={folders}
                onMoveToFolder={(fId) => moveConversationToFolder(c.id, fId)}
                currentFolderId={folders.find((f) => f.conversationIds.includes(c.id))?.id}
                tags={tags[c.id] || []}
                onAddTag={(tag) => addTag(c.id, tag)}
                onRemoveTag={(n) => removeTag(c.id, n)}
                isHighlighted={keyboardSelectIdx === globalIdx}
              />
            );
          })
        )}
      </div>
    </div>
  );
};
