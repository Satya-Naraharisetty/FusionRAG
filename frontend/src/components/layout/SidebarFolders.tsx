import React, { useState } from "react";
import { Folder as FolderIcon, FolderPlus, ChevronRight, ChevronDown, Trash2, Edit } from "lucide-react";
import { Conversation } from "../../types";
import { ConversationItem } from "../sidebar/ConversationItem";
import { Folder, Tag } from "../../hooks/useLocalConversationMetadata";
import { cn } from "../../lib/utils";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "../ui/Modal";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";

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
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>(() => {
    return { "folder-general": true, "folder-research": true };
  });
  const [draggedOverFolderId, setDraggedOverFolderId] = useState<string | null>(null);
  const [showFolderModal, setShowFolderModal] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [renamingFolderId, setRenamingFolderId] = useState<string | null>(null);

  const toggleFolderExpand = (folderId: string) => {
    setExpandedFolders((prev) => ({ ...prev, [folderId]: !prev[folderId] }));
  };

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
    <div className="space-y-1.5 select-none">
      <div className="px-3 flex items-center justify-between text-[10px] font-bold text-zinc-500 dark:text-zinc-550 uppercase tracking-widest">
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

      <div className="space-y-1 px-1">
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
                isDraggedOver && "bg-zinc-800/40 border-zinc-700/30 shadow-sm"
              )}
            >
              {/* Folder Row */}
              <div
                className="flex items-center justify-between px-2.5 py-1.5 hover:bg-zinc-800/30 text-zinc-400 hover:text-zinc-250 rounded-md cursor-pointer transition-all duration-200 group"
                onClick={() => toggleFolderExpand(folder.id)}
              >
                <div className="flex items-center gap-2 min-w-0">
                  {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                  <FolderIcon size={14} className="text-zinc-400" />
                  <span className="text-xs font-medium truncate text-zinc-350">{folder.name}</span>
                  <span className="text-[9px] bg-zinc-800 text-zinc-500 px-1 py-0.5 rounded font-mono font-bold">
                    {nestedDocs.length}
                  </span>
                </div>

                {/* Folder actions */}
                <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setRenamingFolderId(folder.id);
                      setNewFolderName(folder.name);
                      setShowFolderModal(true);
                    }}
                    className="text-zinc-500 hover:text-zinc-350 p-0.5 cursor-pointer"
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
                <div className="pl-3.5 mt-0.5 border-l border-zinc-800/60 ml-4.5 space-y-0.5">
                  {nestedDocs.length === 0 ? (
                    <div className="py-2 text-[10px] text-zinc-650 italic pl-2">
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

      {/* Folder Creation / Rename Dialog */}
      <Dialog open={showFolderModal} onOpenChange={setShowFolderModal}>
        <DialogContent className="bg-[var(--bg-secondary,#171717)] border-[var(--border-color)] text-zinc-200 sm:max-w-md rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-zinc-100 flex items-center gap-2 text-sm font-semibold">
              <FolderIcon size={16} className="text-zinc-400" />
              <span>{renamingFolderId ? "Rename Folder" : "Create Folder"}</span>
            </DialogTitle>
          </DialogHeader>
          <div className="py-2.5">
            <Input
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="Folder name"
              className="text-xs h-10 rounded-xl"
              onKeyDown={(e) => {
                if (e.key === "Enter") handleCreateFolderSubmit();
              }}
            />
          </div>
          <DialogFooter className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => setShowFolderModal(false)}
              className="bg-transparent border-[var(--border-color)] text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 text-xs h-10 rounded-xl"
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateFolderSubmit}
              className="bg-zinc-100 hover:bg-zinc-250 text-zinc-950 text-xs font-semibold h-10 rounded-xl"
            >
              {renamingFolderId ? "Rename" : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
