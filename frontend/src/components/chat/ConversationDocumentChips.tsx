import React, { useCallback } from "react";
import { X, Loader2, Paperclip } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { FileTypeBadge } from "../ui/FileTypeBadge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../ui/tooltip";
import {
  useConversationDocuments,
  useDeleteDocument,
} from "../../hooks/useDocuments";
import { useUploadQueue } from "../../context/UploadQueueContext";
import { QUERY_KEYS } from "../../lib/constants";
import { t } from "../../lib/messages";

interface ConversationDocumentChipsProps {
  conversationId: string | null;
}

/**
 * Server-side chat-scoped documents for a conversation, shown as small chips
 * above the composer so users can see — and remove — what's attached to this
 * chat. The strip makes the two-tier model visible: these files belong to this
 * conversation only (never the global library) and die with it.
 *
 * Removing a chip deletes the document server-side and also drops any matching
 * in-flight upload row from the queue, so a deleted file can't keep spinning
 * in the composer tray. In-flight uploads that the server hasn't persisted yet
 * are surfaced by the composer tray itself, not here.
 */
export const ConversationDocumentChips: React.FC<
  ConversationDocumentChipsProps
> = ({ conversationId }) => {
  const queryClient = useQueryClient();
  const { data: docs = [] } = useConversationDocuments(conversationId);
  const deleteMutation = useDeleteDocument();
  const { queue, cancelUpload } = useUploadQueue();

  const handleRemove = useCallback(
    async (docId: string) => {
      // Drop queue rows still uploading/processing this document (aborts the
      // in-flight request) so the tray doesn't resurrect a deleted file.
      queue
        .filter((q) => q.source === "chat" && q.documentId === docId)
        .forEach((q) => cancelUpload(q.id));
      await deleteMutation.mutateAsync(docId);
      queryClient.invalidateQueries({
        queryKey: [QUERY_KEYS.DOCUMENTS, "conversation", conversationId],
      });
    },
    [queue, cancelUpload, deleteMutation, queryClient, conversationId]
  );

  // The strip is the "chat files" section for this conversation: the
  // lifecycle note is shown even when no files are attached yet, so users
  // know attachments stay in this chat and die with it.
  if (!conversationId) return null;
  const hasDocs = docs.length > 0;

  return (
    <TooltipProvider>
      <div className="w-full max-w-[860px] px-4 sm:px-6">
        {hasDocs && (
          <>
            <div className="mb-1.5 flex items-center gap-1.5 pl-0.5 text-[11px] font-medium text-[var(--text-muted)]">
              <Paperclip size={11} className="flex-shrink-0" />
              <span>{t("chatFiles.header")}</span>
            </div>
            <div className="flex flex-wrap gap-2">
          {docs.map((doc) => {
            const busy =
              doc.status === "pending" || doc.status === "processing";
            return (
              <Tooltip key={doc.id}>
                <TooltipTrigger asChild>
                  <div className="flex select-none items-center gap-1.5 rounded-sm border-y border-r border-l-2 border-l-[var(--accent-tertiary)] border-[var(--border-subtle)] bg-[var(--bg-input)] py-1 pl-2 pr-1 text-xs text-[var(--text-primary)] font-mono uppercase tracking-wider transition-colors">
                    <FileTypeBadge
                      filename={doc.original_filename}
                      variant="minimal"
                      size="sm"
                      className="flex-shrink-0"
                    />
                    <span className="max-w-40 truncate font-medium text-[11px]">
                      {doc.original_filename}
                    </span>
                    {busy && (
                      <Loader2
                        size={11}
                        className="flex-shrink-0 animate-spin text-[var(--text-secondary)]"
                        aria-label="Processing"
                      />
                    )}
                    <button
                      type="button"
                      onClick={() => void handleRemove(doc.id)}
                      disabled={deleteMutation.isPending}
                      className="flex h-5 w-5 cursor-pointer items-center justify-center rounded-full text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-secondary)] hover:text-[var(--accent-error)] disabled:opacity-50"
                      aria-label={t("chatFiles.removeAria", {
                        filename: doc.original_filename,
                      })}
                    >
                      <X size={11} />
                    </button>
                  </div>
                </TooltipTrigger>
                <TooltipContent side="top">
                  {t("chatFiles.tooltip")}
                </TooltipContent>
              </Tooltip>
            );
          })}
            </div>
          </>
        )}
        <div className="mt-1.5 flex items-center gap-1.5 pl-0.5 text-[11px] font-medium leading-snug text-[var(--text-muted)]">
          <Paperclip size={11} className="flex-shrink-0 opacity-60" />
          <span>{t("chatFiles.caption")}</span>
        </div>
      </div>
    </TooltipProvider>
  );
};

export default ConversationDocumentChips;
