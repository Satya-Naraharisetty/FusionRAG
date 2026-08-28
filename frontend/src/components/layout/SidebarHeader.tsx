import React from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { PenSquare, Library, Folder, Search } from "lucide-react";
import { useDocuments } from "../../hooks/useDocuments";
import { useDocumentPipelineSummary } from "../../hooks/useDocumentPipelineSummary";
import { SidebarUploadIndicator } from "./SidebarUploadIndicator";
import { Conversation } from "../../types";
import { cn } from "../../lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../ui/tooltip";

import { useLocale } from "../../lib/messages";

interface SidebarHeaderProps {
  conversations: Conversation[];
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  onNewChat: () => void;
  collapsed: boolean;
}

export const SidebarHeader: React.FC<SidebarHeaderProps> = ({
  searchQuery,
  setSearchQuery,
  onNewChat,
  collapsed,
}) => {
  const { t } = useLocale();
  const navigate = useNavigate();
  const location = useLocation();
  const isDocumentsActive = location.pathname === "/documents";
  const isProjectsActive = location.pathname === "/projects";
  const isNewChatActive = location.pathname === "/chat" || location.pathname === "/";
  const { data: documents = [] } = useDocuments();
  const pipeline = useDocumentPipelineSummary();
  const busy = pipeline.processing > 0;

  const documentsTooltip = busy
    ? `${pipeline.detail ?? "Documents are processing…"} · ${pipeline.progress}%`
    : `${t("nav.documents")} — ${documents.length} file${documents.length === 1 ? "" : "s"}`;

  if (collapsed) {
    return (
      <div className="flex flex-col items-center gap-2 py-3">
        <button
          onClick={onNewChat}
          className={cn(
            "w-10 h-10 rounded-[var(--radius-lg)] flex items-center justify-center cursor-pointer transition-colors",
            isNewChatActive
              ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border-subtle)]"
              : "bg-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
          )}
          title="New Chat"
        >
          <PenSquare size={16} />
        </button>
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={() => navigate("/documents")}
                className={cn(
                  "relative w-10 h-10 rounded-[var(--radius-lg)] flex items-center justify-center cursor-pointer transition-colors",
                  isDocumentsActive
                    ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border-subtle)]"
                    : "bg-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                )}
                aria-label="Library"
              >
                <Library size={16} />
                {busy && (
                  <span className="absolute top-1.5 right-1.5 flex h-2 w-2" aria-hidden="true">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--accent-primary)]/40" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--accent-primary)]" />
                  </span>
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent side="right">{documentsTooltip}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={() => navigate("/projects")}
                className={cn(
                  "w-10 h-10 rounded-[var(--radius-lg)] flex items-center justify-center cursor-pointer transition-colors",
                  isProjectsActive
                    ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border-subtle)]"
                    : "bg-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                )}
                aria-label="Projects"
              >
                <Folder size={16} />
              </button>
            </TooltipTrigger>
            <TooltipContent side="right">Projects</TooltipContent>
          </Tooltip>
        </TooltipProvider>
        {/* Mini upload-queue indicator */}
        <SidebarUploadIndicator collapsed />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1 p-2 pb-1">
      {/* ── New Chat Link ── */}
      <button
        onClick={onNewChat}
        className={cn(
          "w-full h-9 rounded-[var(--radius-lg)] flex items-center gap-3 px-3 cursor-pointer text-[13px] font-medium transition-colors text-left",
          isNewChatActive
            ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border-subtle)] font-semibold"
            : "bg-transparent hover:bg-[var(--bg-tertiary)]/70 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        )}
      >
        <PenSquare size={15} className="flex-shrink-0 text-[var(--text-secondary)]" />
        <span>New chat</span>
      </button>

      {/* ── Library / Documents Link ── */}
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={() => navigate("/documents")}
              className={cn(
                "w-full h-9 rounded-[var(--radius-lg)] flex items-center justify-between px-3 cursor-pointer text-[13px] font-medium transition-colors text-left",
                isDocumentsActive
                  ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border-subtle)] font-semibold"
                  : "bg-transparent hover:bg-[var(--bg-tertiary)]/70 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              )}
            >
              <div className="flex items-center gap-3">
                <span className="relative flex-shrink-0">
                  <Library size={15} className="text-[var(--text-secondary)]" />
                  {busy && (
                    <span className="absolute -top-1 -right-1 flex h-2 w-2" aria-hidden="true">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--accent-primary)]/40" />
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--accent-primary)]" />
                    </span>
                  )}
                </span>
                <span>Library</span>
              </div>
              <span className="text-[10px] font-mono font-medium text-[var(--text-muted)] bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] px-1.5 py-0.2 rounded flex-shrink-0">
                {documents.length}
              </span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="right">{documentsTooltip}</TooltipContent>
        </Tooltip>
      </TooltipProvider>

      {/* ── Projects Link ── */}
      <button
        onClick={() => navigate("/projects")}
        className={cn(
          "w-full h-9 rounded-[var(--radius-lg)] flex items-center gap-3 px-3 cursor-pointer text-[13px] font-medium transition-colors text-left",
          isProjectsActive
            ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border-subtle)] font-semibold"
            : "bg-transparent hover:bg-[var(--bg-tertiary)]/70 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        )}
      >
        <Folder size={15} className={cn("flex-shrink-0", isProjectsActive ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]")} />
        <span>Projects</span>
      </button>

      {/* Mini upload-queue indicator */}
      <SidebarUploadIndicator collapsed={false} />

      {/* Search Box */}
      <div className="relative flex items-center mt-1 mb-1">
        <Search
          size={13}
          className="absolute left-3 text-[var(--text-muted)] pointer-events-none flex-shrink-0"
        />
        <input
          id="sidebar-search-input"
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setSearchQuery("");
          }}
          placeholder={t("nav.searchPlaceholder")}
          className="w-full h-8 bg-[var(--bg-input)] border border-[var(--border-default)] hover:border-[var(--border-hover)] rounded-[var(--radius-lg)] pl-8 pr-12 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none focus:border-[var(--accent-primary)]/50 focus:ring-2 focus:ring-[var(--accent-primary)]/20 transition-all"
        />
        {/* Keyboard shortcut hint */}
        <span className="absolute right-2 flex items-center">
          <kbd className="text-[9px] font-mono text-[var(--text-muted)] bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] rounded px-1.2 py-0.5 leading-none">
            Ctrl + /
          </kbd>
        </span>
      </div>
    </div>
  );
};
