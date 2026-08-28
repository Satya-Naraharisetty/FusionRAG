import React, { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Folder as FolderIcon,
  Search,
  Plus,
  MoreVertical,
  Edit2,
  Trash2,
  MessageSquare,
  ChevronRight,
  FolderMinus,
  Sparkles,
} from "lucide-react";
import { useLocalConversationMetadata } from "../hooks/useLocalConversationMetadata";
import { useConversations } from "../hooks/useConversations";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "../components/ui/Modal";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../components/ui/Dropdown";
import { cn } from "../lib/utils";

type FilterTab = "all" | "created" | "shared";

export const ProjectsPage: React.FC = () => {
  const navigate = useNavigate();
  const { data: convData } = useConversations();
  const {
    folders,
    createFolder,
    renameFolder,
    deleteFolder,
    moveConversationToFolder,
  } = useLocalConversationMetadata();

  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<FilterTab>("all");
  const [showModal, setShowModal] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [renamingFolderId, setRenamingFolderId] = useState<string | null>(null);

  const conversationMap = useMemo(() => {
    const list = convData?.conversations ?? [];
    return new Map(list.map((c) => [c.id, c]));
  }, [convData?.conversations]);

  const filteredFolders = useMemo(() => {
    if (activeTab === "shared") return [];
    let list = folders;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter((f) => {
        const matchesName = f.name.toLowerCase().includes(q);
        const matchesChildChat = f.conversationIds.some((id) => {
          const c = conversationMap.get(id);
          return c && c.title.toLowerCase().includes(q);
        });
        return matchesName || matchesChildChat;
      });
    }
    return list;
  }, [folders, searchQuery, activeTab, conversationMap]);

  const handleOpenCreate = () => {
    setRenamingFolderId(null);
    setNewProjectName("");
    setShowModal(true);
  };

  const handleOpenRename = (folder: { id: string; name: string }) => {
    setRenamingFolderId(folder.id);
    setNewProjectName(folder.name);
    setShowModal(true);
  };

  const handleSubmitModal = () => {
    const trimmed = newProjectName.trim();
    if (!trimmed) return;
    if (renamingFolderId) {
      renameFolder(renamingFolderId, trimmed);
    } else {
      createFolder(trimmed);
    }
    setNewProjectName("");
    setRenamingFolderId(null);
    setShowModal(false);
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-[var(--bg-primary)] overflow-y-auto select-none">
      <div className="max-w-5xl w-full mx-auto px-6 py-8 flex flex-col gap-6">
        {/* ── Top Header Row ── */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="font-title text-2xl sm:text-3xl font-bold tracking-tight text-[var(--text-primary)]">
              Projects
            </h1>
            <p className="text-xs text-[var(--text-muted)] mt-1">
              Organize your conversations, research notes, and domain context into folders.
            </p>
          </div>

          <div className="flex items-center gap-3">
            {/* Search bar */}
            <div className="relative flex items-center">
              <Search
                size={14}
                className="absolute left-3 text-[var(--text-muted)] pointer-events-none"
              />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search projects & chats"
                className="h-8.5 w-48 sm:w-60 bg-[var(--bg-input)] border border-[var(--border-default)] hover:border-[var(--border-hover)] rounded-full pl-8 pr-3 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none focus:border-[var(--accent-primary)]/50 focus:ring-2 focus:ring-[var(--accent-primary)]/20 transition-all"
              />
            </div>

            {/* New Project Button */}
            <button
              onClick={handleOpenCreate}
              className="h-8.5 px-4 rounded-full bg-white text-zinc-950 dark:bg-zinc-100 dark:text-zinc-900 hover:bg-zinc-200 dark:hover:bg-zinc-200 text-xs font-semibold flex items-center gap-1.5 shadow-xs transition-colors cursor-pointer"
            >
              <Plus size={14} />
              <span>New</span>
            </button>
          </div>
        </div>

        {/* ── Filter Tabs ── */}
        <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] pb-3">
          {(
            [
              { id: "all", label: "All" },
              { id: "created", label: "Created by you" },
              { id: "shared", label: "Shared with you" },
            ] as const
          ).map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "px-3.5 py-1.5 rounded-full text-xs font-medium transition-colors cursor-pointer",
                activeTab === tab.id
                  ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border-subtle)] font-semibold"
                  : "text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]/50"
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* ── Content View ── */}
        {filteredFolders.length === 0 ? (
          <div className="flex flex-col items-center justify-center min-h-[360px] gap-3 text-center">
            <div className="w-14 h-14 rounded-2xl bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] flex items-center justify-center text-[var(--text-muted)] shadow-xs">
              <FolderIcon size={26} />
            </div>
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {activeTab === "shared"
                ? "No shared projects yet"
                : searchQuery
                ? "No matching projects found"
                : "No projects yet"}
            </p>
            <p className="text-xs text-[var(--text-muted)] max-w-sm">
              {activeTab === "shared"
                ? "Projects shared by teammates will appear here."
                : "Create a project to group and organize chats into dedicated workspaces."}
            </p>
            {activeTab !== "shared" && (
              <button
                onClick={handleOpenCreate}
                className="mt-2 h-8 px-4 rounded-full bg-[var(--bg-tertiary)] hover:bg-[var(--bg-elevated)] border border-[var(--border-default)] text-xs font-medium text-[var(--text-primary)] transition-colors cursor-pointer"
              >
                + Create project
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-2">
            {filteredFolders.map((folder) => {
              const nestedConvs = folder.conversationIds
                .map((id) => conversationMap.get(id))
                .filter((c) => !!c);

              return (
                <div
                  key={folder.id}
                  className="group relative flex flex-col justify-between p-4 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border-default)] hover:border-[var(--border-hover)] hover:shadow-xs transition-all min-h-[200px]"
                >
                  <div>
                    {/* Header: Icon + Name + Menu */}
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="w-8 h-8 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] flex items-center justify-center text-[var(--accent-primary)] flex-shrink-0">
                          <FolderIcon size={16} />
                        </div>
                        <h2 className="text-sm font-semibold text-[var(--text-primary)] truncate">
                          {folder.name}
                        </h2>
                      </div>

                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <button
                            className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors cursor-pointer"
                            aria-label="Project actions"
                          >
                            <MoreVertical size={14} />
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-40">
                          <DropdownMenuItem
                            onClick={() => handleOpenRename(folder)}
                            className="gap-2 cursor-pointer"
                          >
                            <Edit2 size={13} />
                            <span>Rename</span>
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={() => deleteFolder(folder.id)}
                            className="gap-2 text-[var(--accent-error)] focus:bg-red-500/10 focus:text-red-400 cursor-pointer"
                          >
                            <Trash2 size={13} />
                            <span>Delete</span>
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>

                    <p className="text-xs text-[var(--text-muted)] mb-3">
                      {nestedConvs.length === 1
                        ? "1 conversation"
                        : `${nestedConvs.length} conversations`}
                    </p>

                    {/* Preview of conversations */}
                    {nestedConvs.length > 0 ? (
                      <div className="flex flex-col gap-1">
                        {nestedConvs.map((c) => (
                          <div
                            key={c!.id}
                            className="group/item flex items-center justify-between px-2 py-1.5 rounded-md text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] cursor-pointer transition-colors"
                          >
                            <div
                              onClick={() => navigate(`/chat/${c!.id}`)}
                              className="flex items-center gap-2 truncate flex-1 min-w-0"
                            >
                              <MessageSquare size={12} className="text-[var(--text-muted)] flex-shrink-0" />
                              <span className="truncate">{c!.title}</span>
                            </div>
                            <div className="flex items-center gap-1">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  moveConversationToFolder(c!.id, null);
                                }}
                                title="Remove from folder"
                                className="opacity-0 group-hover/item:opacity-100 text-[var(--text-muted)] hover:text-amber-400 p-0.5 rounded transition-opacity"
                              >
                                <FolderMinus size={11} />
                              </button>
                              <ChevronRight
                                size={12}
                                className="text-[var(--text-muted)] opacity-50 flex-shrink-0"
                              />
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="py-4 text-center">
                        <p className="text-xs text-[var(--text-muted)] italic">
                          No chats inside this folder yet.
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Footer Action */}
                  <div className="pt-3 mt-3 border-t border-[var(--border-subtle)]/50 flex items-center justify-between text-xs text-[var(--text-muted)]">
                    <span className="flex items-center gap-1 text-[11px]">
                      <Sparkles size={11} className="text-[var(--accent-primary)]" />
                      Project
                    </span>
                    <button
                      onClick={() => navigate("/chat")}
                      className="text-[var(--accent-primary)] hover:underline font-medium cursor-pointer"
                    >
                      New chat →
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Create / Rename Dialog ── */}
      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-sm">
              <FolderIcon size={16} className="text-[var(--text-muted)]" />
              {renamingFolderId ? "Rename Project" : "New Project"}
            </DialogTitle>
          </DialogHeader>
          <div className="py-3">
            <Input
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              placeholder="Project name (e.g. Research, Q3 Marketing)"
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSubmitModal();
              }}
              autoFocus
            />
          </div>
          <DialogFooter className="gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowModal(false)}
            >
              Cancel
            </Button>
            <Button variant="default" size="sm" onClick={handleSubmitModal}>
              {renamingFolderId ? "Rename" : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ProjectsPage;
