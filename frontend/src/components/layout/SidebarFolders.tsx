import React, { useState } from "react";
import { Folder as FolderIcon, FolderPlus, ChevronRight, ChevronDown, Trash2, Edit } from "lucide-react";
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
    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }} className="select-none">
      {/* FOLDERS section header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "4px 4px 2px",
          fontSize: "11px",
          fontWeight: 600,
          color: "var(--text-muted, #737373)",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
        }}
      >
        <span>Folders</span>
        <button
          onClick={() => {
            setRenamingFolderId(null);
            setNewFolderName("");
            setShowFolderModal(true);
          }}
          style={{
            background: "none",
            border: "none",
            color: "var(--text-muted, #737373)",
            cursor: "pointer",
            padding: "2px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            borderRadius: "4px",
            transition: "color 0.15s",
          }}
          className="hover:text-zinc-300"
          title="Create Folder"
        >
          <FolderPlus size={13} />
        </button>
      </div>

      {/* Folder list */}
      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
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
              style={{
                borderRadius: "8px",
                border: isDraggedOver ? "1px solid rgba(255,255,255,0.10)" : "1px solid transparent",
                background: isDraggedOver ? "rgba(255,255,255,0.04)" : "transparent",
                transition: "all 0.15s ease",
              }}
            >
              {/* Folder Row */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "0 8px",
                  height: "34px",
                  borderRadius: "8px",
                  cursor: "pointer",
                  color: "var(--text-secondary, #A3A3A3)",
                  transition: "all 0.15s ease",
                }}
                className="hover:bg-white/[0.05] hover:text-zinc-200 group"
                onClick={() => toggleFolderExpand(folder.id)}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "7px", minWidth: 0 }}>
                  <span style={{ color: "var(--text-muted, #737373)", flexShrink: 0 }}>
                    {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                  </span>
                  <FolderIcon size={13} style={{ color: "var(--text-muted, #737373)", flexShrink: 0 }} />
                  <span
                    style={{
                      fontSize: "13px",
                      fontWeight: 500,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {folder.name}
                  </span>
                  <span
                    style={{
                      fontSize: "11px",
                      fontFamily: "monospace",
                      fontWeight: 600,
                      color: "var(--text-muted, #737373)",
                      flexShrink: 0,
                    }}
                  >
                    {nestedDocs.length > 0 ? nestedDocs.length : ""}
                  </span>
                </div>

                {/* Folder actions — shown on hover */}
                <div
                  style={{ display: "flex", alignItems: "center", gap: "4px" }}
                  className="opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                >
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setRenamingFolderId(folder.id);
                      setNewFolderName(folder.name);
                      setShowFolderModal(true);
                    }}
                    style={{
                      background: "none",
                      border: "none",
                      color: "var(--text-muted, #737373)",
                      cursor: "pointer",
                      padding: "3px",
                      borderRadius: "4px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      transition: "color 0.15s",
                    }}
                    className="hover:text-zinc-300"
                    title="Rename folder"
                  >
                    <Edit size={11} />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteFolder(folder.id);
                    }}
                    style={{
                      background: "none",
                      border: "none",
                      color: "var(--text-muted, #737373)",
                      cursor: "pointer",
                      padding: "3px",
                      borderRadius: "4px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      transition: "color 0.15s",
                    }}
                    className="hover:text-red-400"
                    title="Delete folder"
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              </div>

              {/* Nested conversations */}
              {isExpanded && (
                <div
                  style={{
                    paddingLeft: "20px",
                    marginTop: "2px",
                    borderLeft: "1px solid rgba(255,255,255,0.06)",
                    marginLeft: "20px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "1px",
                  }}
                >
                  {nestedDocs.length === 0 ? (
                    <div
                      style={{
                        padding: "10px 8px",
                        fontSize: "12px",
                        color: "var(--text-muted, #737373)",
                        fontStyle: "italic",
                      }}
                    >
                      No conversations yet
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
              className="text-sm h-10 rounded-xl"
              onKeyDown={(e) => {
                if (e.key === "Enter") handleCreateFolderSubmit();
              }}
            />
          </div>
          <DialogFooter className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => setShowFolderModal(false)}
              className="bg-transparent border-[var(--border-color)] text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 text-sm h-10 rounded-xl"
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateFolderSubmit}
              className="bg-zinc-100 hover:bg-zinc-250 text-zinc-950 text-sm font-semibold h-10 rounded-xl"
            >
              {renamingFolderId ? "Rename" : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
