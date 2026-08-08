import React, { useState } from "react";
import {
  Folder as FolderIcon,
  FolderPlus,
  ChevronRight,
  ChevronDown,
  Trash2,
  Edit,
} from "lucide-react";
import { Conversation } from "../../types";
import { ConversationItem } from "../sidebar/ConversationItem";
import { Folder, Tag } from "../../hooks/useLocalConversationMetadata";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "../ui/Modal";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import { cn } from "@/lib/utils";

interface SidebarFoldersProps {
  folders: Folder[];
  folderConversations: Record<string, Conversation[]>;
  activeId: string | null;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => Promise<unknown>;
  onDelete: (id: string) => Promise<unknown>;
  pinnedIds: string[];
  tags: Record<string, Tag[]>;
  togglePin: (id: string) => void;
  createFolder: (name: string) => void;
  renameFolder: (id: string, name: string) => void;
  deleteFolder: (id: string) => void;
  moveConversationToFolder: (conversationId: string, folderId: string | null) => void;
  addTag: (conversationId: string, tag: Tag) => void;
  removeTag: (conversationId: string, name: string) => void;
  keyboardSelectIdx: number;
  flatVisibleConversations: Conversation[];
}

export const SidebarFolders: React.FC<SidebarFoldersProps> = ({
  folders,
  folderConversations,
  activeId,
  onSelect,
  onRename,
  onDelete,
  pinnedIds,
  tags,
  togglePin,
  createFolder,
  renameFolder,
  deleteFolder,
  moveConversationToFolder,
  addTag,
  removeTag,
  keyboardSelectIdx,
  flatVisibleConversations,
}) => {
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>({
    "folder-general":  true,
    "folder-research": true,
  });
  const [draggedOverFolderId, setDraggedOverFolderId] = useState<string | null>(null);
  const [showFolderModal, setShowFolderModal]         = useState(false);
  const [newFolderName, setNewFolderName]             = useState("");
  const [renamingFolderId, setRenamingFolderId]       = useState<string | null>(null);

  const toggleExpand = (id: string) =>
    setExpandedFolders((prev) => ({ ...prev, [id]: !prev[id] }));

  const handleDragOver  = (e: React.DragEvent, id: string) => { e.preventDefault(); setDraggedOverFolderId(id); };
  const handleDragLeave = () => setDraggedOverFolderId(null);
  const handleDrop      = (e: React.DragEvent, folderId: string | null) => {
    e.preventDefault();
    setDraggedOverFolderId(null);
    const convId = e.dataTransfer.getData("text/plain");
    if (convId) moveConversationToFolder(convId, folderId);
  };

  const handleSubmit = () => {
    const trimmed = newFolderName.trim();
    if (!trimmed) return;
    if (renamingFolderId) renameFolder(renamingFolderId, trimmed);
    else                  createFolder(trimmed);
    setNewFolderName("");
    setRenamingFolderId(null);
    setShowFolderModal(false);
  };

  if (folders.length === 0) return null;

  return (
    <>
      <div className="flex flex-col gap-0.5 select-none">
        {/* Section header */}
        <div className="flex items-center justify-between px-1 py-1.5">
          <span className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider">
            Folders
          </span>
          <button
            onClick={() => { setRenamingFolderId(null); setNewFolderName(""); setShowFolderModal(true); }}
            className="text-[var(--text-muted)] hover:text-[var(--text-primary)] p-0.5 rounded cursor-pointer transition-colors"
            title="New folder"
            aria-label="Create new folder"
          >
            <FolderPlus size={13} />
          </button>
        </div>

        {/* Folder list */}
        <div className="flex flex-col gap-0.5">
          {folders.map((folder) => {
            const nested     = folderConversations[folder.id] || [];
            const isExpanded = expandedFolders[folder.id];
            const isDragOver = draggedOverFolderId === folder.id;

            return (
              <div
                key={folder.id}
                onDragOver={(e) => handleDragOver(e, folder.id)}
                onDragLeave={handleDragLeave}
                onDrop={(e) => handleDrop(e, folder.id)}
                className={cn(
                  "rounded-[var(--radius-md)] transition-colors",
                  isDragOver && "bg-[var(--bg-tertiary)] ring-1 ring-[var(--border-hover)]"
                )}
              >
                {/* Folder row */}
                <div
                  className="flex items-center justify-between px-2 h-8 rounded-[var(--radius-md)] cursor-pointer text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]/60 transition-colors group"
                  onClick={() => toggleExpand(folder.id)}
                  role="button"
                  aria-expanded={isExpanded}
                  aria-label={`${folder.name} folder`}
                >
                  <div className="flex items-center gap-1.5 min-w-0 flex-1">
                    <span className="text-[var(--text-muted)] flex-shrink-0">
                      {isExpanded
                        ? <ChevronDown size={12} />
                        : <ChevronRight size={12} />}
                    </span>
                    <FolderIcon size={12} className="text-[var(--text-muted)] flex-shrink-0" />
                    <span className="text-[13px] font-medium truncate">{folder.name}</span>
                    {nested.length > 0 && (
                      <span className="text-[10px] font-mono text-[var(--text-muted)] flex-shrink-0">
                        {nested.length}
                      </span>
                    )}
                  </div>

                  {/* Hover actions */}
                  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setRenamingFolderId(folder.id);
                        setNewFolderName(folder.name);
                        setShowFolderModal(true);
                      }}
                      className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] cursor-pointer transition-colors"
                      title="Rename folder"
                      aria-label={`Rename ${folder.name}`}
                    >
                      <Edit size={11} />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); deleteFolder(folder.id); }}
                      className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--accent-error)] hover:bg-red-500/10 cursor-pointer transition-colors"
                      title="Delete folder"
                      aria-label={`Delete ${folder.name}`}
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>
                </div>

                {/* Nested conversations */}
                {isExpanded && (
                  <div className="ml-5 pl-2.5 border-l border-[var(--border-subtle)] mt-0.5 mb-1 flex flex-col gap-0.5">
                    {nested.length === 0 ? (
                      <p className="py-2 px-2 text-[11px] text-[var(--text-muted)] italic">
                        No conversations yet
                      </p>
                    ) : (
                      nested.map((c) => {
                        const globalIdx = flatVisibleConversations.findIndex((v) => v.id === c.id);
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
                            onRemoveTag={(name) => removeTag(c.id, name)}
                            isHighlighted={keyboardSelectIdx === globalIdx}
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

      {/* Create / Rename folder dialog */}
      <Dialog open={showFolderModal} onOpenChange={setShowFolderModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-sm">
              <FolderIcon size={14} className="text-[var(--text-muted)]" />
              {renamingFolderId ? "Rename Folder" : "Create Folder"}
            </DialogTitle>
          </DialogHeader>
          <div className="py-2">
            <Input
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="Folder name"
              onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
              autoFocus
            />
          </div>
          <DialogFooter className="gap-2">
            <Button variant="secondary" size="sm" onClick={() => setShowFolderModal(false)}>
              Cancel
            </Button>
            <Button variant="default" size="sm" onClick={handleSubmit}>
              {renamingFolderId ? "Rename" : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};
