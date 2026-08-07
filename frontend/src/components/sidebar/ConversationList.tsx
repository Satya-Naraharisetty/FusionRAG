import React, { useMemo, useState, useEffect } from "react";
import { Folder as FolderIcon, FolderPlus, ChevronRight, ChevronDown, Trash2, Edit, Pin } from "lucide-react";
import { Conversation } from "../../types";
import { ConversationItem } from "./ConversationItem";
import { Folder, Tag } from "../../hooks/useLocalConversationMetadata";
import { isToday, isYesterday, subDays, isAfter } from "date-fns";
import { cn } from "../../lib/utils";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

interface ConversationListProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => Promise<unknown>;
  onDelete: (id: string) => Promise<unknown>;
  searchQuery: string;

  // Local metadata props passed down from Sidebar
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

export const ConversationList: React.FC<ConversationListProps> = ({
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
  // Folder UI state
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>(() => {
    return { "folder-general": true, "folder-research": true };
  });
  const [draggedOverFolderId, setDraggedOverFolderId] = useState<string | null>(null);

  // Folder modal state
  const [showFolderModal, setShowFolderModal] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [renamingFolderId, setRenamingFolderId] = useState<string | null>(null);

  // Keyboard navigation state
  const [keyboardSelectIdx, setKeyboardSelectIdx] = useState<number>(-1);

  const toggleFolderExpand = (folderId: string) => {
    setExpandedFolders((prev) => ({ ...prev, [folderId]: !prev[folderId] }));
  };

  // Helper lists
  const conversationMap = useMemo(() => {
    return new Map(conversations.map((c) => [c.id, c]));
  }, [conversations]);

  // Filtered conversations based on search
  const filteredConversations = useMemo(() => {
    if (!searchQuery.trim()) return conversations;
    const lower = searchQuery.toLowerCase();
    return conversations.filter((c) => c.title.toLowerCase().includes(lower));
  }, [conversations, searchQuery]);

  // Folder contents mapping
  const folderConversations = useMemo(() => {
    const map: Record<string, Conversation[]> = {};
    folders.forEach((f) => {
      map[f.id] = f.conversationIds
        .map((id) => conversationMap.get(id))
        .filter((c): c is Conversation => !!c && (!searchQuery.trim() || c.title.toLowerCase().includes(searchQuery.toLowerCase())));
    });
    return map;
  }, [folders, conversationMap, searchQuery]);

  // Foldered IDs set for quick check
  const folderedConversationIds = useMemo(() => {
    const set = new Set<string>();
    folders.forEach((f) => {
      f.conversationIds.forEach((id) => set.add(id));
    });
    return set;
  }, [folders]);

  // Pinned conversations
  const pinnedConversations = useMemo(() => {
    return pinnedIds
      .map((id) => conversationMap.get(id))
      .filter((c): c is Conversation => !!c && (!searchQuery.trim() || c.title.toLowerCase().includes(searchQuery.toLowerCase())));
  }, [pinnedIds, conversationMap, searchQuery]);

  // Un-foldered conversations
  const unfolderedConversations = useMemo(() => {
    return filteredConversations.filter((c) => !folderedConversationIds.has(c.id));
  }, [filteredConversations, folderedConversationIds]);

  // Group un-foldered conversations by date
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

  // Flat list of visible conversations for keyboard navigation
  const flatVisibleConversations = useMemo(() => {
    const list: Conversation[] = [];

    // Pinned
    pinnedConversations.forEach((c) => list.push(c));

    // Folders
    folders.forEach((folder) => {
      if (expandedFolders[folder.id]) {
        const nested = folderConversations[folder.id] || [];
        nested.forEach((c) => list.push(c));
      }
    });

    // Unfoldered
    const { today, yesterday, last7Days, older } = unfolderedGroups;
    [...today, ...yesterday, ...last7Days, ...older].forEach((c) => {
      // Avoid adding duplicate if it was already in pinned
      if (!list.some((existing) => existing.id === c.id)) {
        list.push(c);
      }
    });

    return list;
  }, [pinnedConversations, folders, folderConversations, expandedFolders, unfolderedGroups]);

  // Key navigation listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Skip if typing in inputs
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
      } else if (e.key === "p" && e.ctrlKey && keyboardSelectIdx >= 0) {
        e.preventDefault();
        const selected = flatVisibleConversations[keyboardSelectIdx];
        if (selected) togglePin(selected.id);
      } else if (e.key === "Delete" && keyboardSelectIdx >= 0) {
        e.preventDefault();
        const selected = flatVisibleConversations[keyboardSelectIdx];
        if (selected) {
          onDelete(selected.id);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [flatVisibleConversations, keyboardSelectIdx, onSelect, togglePin, onDelete]);

  // Adjust active selected index dynamically
  useEffect(() => {
    if (activeId) {
      const idx = flatVisibleConversations.findIndex((c) => c.id === activeId);
      if (idx !== -1) {
        setKeyboardSelectIdx(idx);
      }
    }
  }, [activeId, flatVisibleConversations]);

  // Drag over dropzones
  const handleDragOver = (e: React.DragEvent, folderId: string | null) => {
    e.preventDefault();
    setDraggedOverFolderId(folderId);
  };

  const handleDragLeave = () => {
    setDraggedOverFolderId(null);
  };

  const handleDrop = (e: React.DragEvent, folderId: string | null) => {
    e.preventDefault();
    setDraggedOverFolderId(null);
    const conversationId = e.dataTransfer.getData("text/plain");
    if (conversationId) {
      moveConversationToFolder(conversationId, folderId);
    }
  };

  const handleCreateFolderSubmit = () => {
    const trimmed = newFolderName.trim();
    if (!trimmed) return;
    if (renamingFolderId) {
      renameFolder(renamingFolderId, trimmed);
    } else {
      createFolder(trimmed);
    }
    setNewFolderName("");
    setRenamingFolderId(null);
    setShowFolderModal(false);
  };

  return (
    <div className="flex-1 w-full overflow-y-auto px-2 py-1 space-y-4 scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent">
      {/* Pinned Category */}
      {pinnedConversations.length > 0 && (
        <div className="space-y-1.5">
          <div className="px-3 text-[10px] font-bold text-amber-500 uppercase tracking-wider flex items-center gap-1.5 select-none">
            <Pin size={10} className="fill-current" />
            <span>Pinned</span>
          </div>
          <div className="space-y-0.5">
            {pinnedConversations.map((c, index) => (
              <ConversationItem
                key={`pinned-${c.id}`}
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
                isHighlighted={keyboardSelectIdx === index}
              />
            ))}
          </div>
        </div>
      )}

      {/* Folders Section */}
      <div className="space-y-2">
        <div className="px-3 flex items-center justify-between text-[10px] font-bold text-zinc-500 uppercase tracking-wider select-none">
          <span>Folders</span>
          <button
            onClick={() => {
              setRenamingFolderId(null);
              setNewFolderName("");
              setShowFolderModal(true);
            }}
            className="text-zinc-500 hover:text-zinc-300 transition-colors duration-200 cursor-pointer"
            title="Create Folder"
          >
            <FolderPlus size={13} />
          </button>
        </div>

        <div className="space-y-1">
          {folders.map((folder) => {
            const nestedDocs = folderConversations[folder.id] || [];
            const isExpanded = expandedFolders[folder.id];
            const isDraggedOver = draggedOverFolderId === folder.id;

            return (
              <div
                key={folder.id}
                onDragOver={(e) => handleDragOver(e, folder.id)}
                onDragLeave={handleDragLeave}
                onDrop={(e) => handleDrop(e, folder.id)}
                className={cn(
                  "rounded-lg border border-transparent transition-all duration-200",
                  isDraggedOver && "bg-violet-950/20 border-violet-800/40 shadow-sm"
                )}
              >
                {/* Folder Row */}
                <div
                  className="flex items-center justify-between px-3 py-1.5 hover:bg-zinc-900/40 text-zinc-400 hover:text-zinc-300 rounded-md cursor-pointer transition-all duration-200 group"
                  onClick={() => toggleFolderExpand(folder.id)}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    <FolderIcon size={14} className="text-violet-400" />
                    <span className="text-xs font-bold truncate text-zinc-300">{folder.name}</span>
                    <span className="text-[9px] bg-zinc-900 px-1.5 py-0.5 rounded text-zinc-500 font-mono font-bold">
                      {nestedDocs.length}
                    </span>
                  </div>

                  {/* Folder action controls */}
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setRenamingFolderId(folder.id);
                        setNewFolderName(folder.name);
                        setShowFolderModal(true);
                      }}
                      className="text-zinc-500 hover:text-zinc-300 p-0.5 cursor-pointer"
                      title="Rename folder"
                    >
                      <Edit size={11} />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteFolder(folder.id);
                      }}
                      className="text-zinc-500 hover:text-red-400 p-0.5 cursor-pointer"
                      title="Delete folder"
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>
                </div>

                {/* Folder nested conversations */}
                {isExpanded && (
                  <div className="pl-4 mt-0.5 border-l border-zinc-900 ml-5.5 space-y-0.5">
                    {nestedDocs.length === 0 ? (
                      <div className="py-2 text-[10px] text-zinc-600 italic select-none">
                        Drag conversations here
                      </div>
                    ) : (
                      nestedDocs.map((c) => {
                        const globalIndex = flatVisibleConversations.findIndex((vis) => vis.id === c.id);
                        return (
                          <ConversationItem
                            key={`folder-${folder.id}-${c.id}`}
                            conversation={c}
                            isActive={c.id === activeId}
                            onSelect={() => onSelect(c.id)}
                            onRename={onRename}
                            onDelete={onDelete}
                            isPinned={pinnedIds.includes(c.id)}
                            onTogglePin={() => togglePin(c.id)}
                            folders={folders}
                            onMoveToFolder={(fId) => moveConversationToFolder(c.id, fId)}
                            currentFolderId={folder.id}
                            tags={tags[c.id] || []}
                            onAddTag={(tag) => addTag(c.id, tag)}
                            onRemoveTag={(tName) => removeTag(c.id, tName)}
                            isHighlighted={keyboardSelectIdx === globalIndex}
                          />
                        );
                      })
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Date-grouped Un-foldered Category */}
      <div
        className="space-y-4"
        onDragOver={(e) => handleDragOver(e, null)}
        onDragLeave={handleDragLeave}
        onDrop={(e) => handleDrop(e, null)}
      >
        {Object.entries(unfolderedGroups).map(([groupKey, groupDocs]) => {
          if (groupDocs.length === 0) return null;

          const groupLabels: Record<string, string> = {
            today: "Today",
            yesterday: "Yesterday",
            last7Days: "Previous 7 Days",
            older: "Older Conversations",
          };

          return (
            <div key={groupKey} className="space-y-1">
              <div className="px-3 text-[10px] font-bold text-zinc-500 uppercase tracking-wider select-none">
                {groupLabels[groupKey]}
              </div>
              <div className="space-y-0.5">
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

      {/* Folder Creation / Rename Dialog */}
      <Dialog open={showFolderModal} onOpenChange={setShowFolderModal}>
        <DialogContent className="bg-zinc-950 border-zinc-800 text-zinc-200 sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-zinc-100 flex items-center gap-2">
              <FolderIcon size={18} className="text-violet-500" />
              <span>{renamingFolderId ? "Rename Folder" : "Create Folder"}</span>
            </DialogTitle>
          </DialogHeader>
          <div className="py-3">
            <Input
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="e.g. Finance Reports, Research, Homework"
              className="bg-zinc-900 border-zinc-800 text-zinc-200 text-xs focus-visible:ring-1 focus-visible:ring-violet-600"
              onKeyDown={(e) => {
                if (e.key === "Enter") handleCreateFolderSubmit();
              }}
            />
          </div>
          <DialogFooter className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => setShowFolderModal(false)}
              className="bg-transparent border-zinc-800 text-zinc-300 hover:bg-zinc-900 hover:text-zinc-100 text-xs"
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateFolderSubmit}
              className="bg-violet-600 hover:bg-violet-750 text-white text-xs font-semibold"
            >
              {renamingFolderId ? "Rename" : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
