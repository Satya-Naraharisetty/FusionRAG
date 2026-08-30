import React from "react";
import { X, FileText, ExternalLink, Check, Copy, ShieldCheck, Database } from "lucide-react";
import { Citation } from "../../types";
import { Button } from "../ui/Button";
import { FileTypeBadge } from "../ui/FileTypeBadge";
import { useNavigate } from "react-router-dom";

interface CitationDrawerProps {
  citation: Citation | null;
  isOpen: boolean;
  onClose: () => void;
}

export const CitationDrawer: React.FC<CitationDrawerProps> = ({
  citation,
  isOpen,
  onClose,
}) => {
  const navigate = useNavigate();
  const [copied, setCopied] = React.useState(false);

  if (!isOpen || !citation) return null;

  const handleCopyChunkId = () => {
    navigator.clipboard.writeText(citation.chunk_id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleOpenDocument = () => {
    onClose();
    navigate("/documents");
  };

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs transition-opacity animate-fade-in"
        aria-hidden="true"
      />

      {/* Drawer Panel */}
      <aside
        role="dialog"
        aria-label="Source Citation Details"
        className="fixed inset-y-0 right-0 z-50 w-full max-w-md bg-[var(--bg-secondary)] border-l border-[var(--border-subtle)] shadow-2xl flex flex-col animate-slide-in-right duration-200"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border-subtle)] bg-[var(--bg-tertiary)]/50">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="h-8 w-8 rounded-[var(--radius-md)] bg-[var(--accent-primary)]/10 border border-[var(--accent-primary)]/20 flex items-center justify-center text-[var(--accent-primary)] flex-shrink-0">
              <FileText size={16} />
            </div>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-[var(--text-primary)] truncate">
                Source Citation
              </h2>
              <p className="text-[11px] text-[var(--text-muted)] truncate">
                {citation.document_name}
              </p>
            </div>
          </div>

          <Button
            variant="ghost"
            size="iconSm"
            onClick={onClose}
            className="text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            aria-label="Close drawer"
          >
            <X size={18} />
          </Button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-4 text-xs">
          {/* Document Summary Card */}
          <div className="p-3.5 rounded-[var(--radius-lg)] bg-[var(--bg-tertiary)]/40 border border-[var(--border-subtle)] flex flex-col gap-2.5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
                Document Info
              </span>
              <FileTypeBadge filename={citation.document_name} />
            </div>

            <div className="text-sm font-medium text-[var(--text-primary)] break-all">
              {citation.document_name}
            </div>

            {citation.version !== undefined && (
              <div className="flex items-center gap-2 text-[11px] text-[var(--text-secondary)]">
                <span className="px-1.5 py-0.5 rounded bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[10px]">
                  Version {citation.version}
                </span>
                {citation.element_type && (
                  <span className="px-1.5 py-0.5 rounded bg-blue-500/10 border border-blue-500/20 text-blue-400 text-[10px]">
                    {citation.element_type}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Retrieval Confidence & Entailment */}
          <div className="grid grid-cols-2 gap-2.5">
            <div className="p-3 rounded-[var(--radius-lg)] bg-[var(--bg-tertiary)]/40 border border-[var(--border-subtle)]">
              <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider block mb-1">
                Relevance Score
              </span>
              <span className="text-base font-semibold text-[var(--accent-primary)] font-mono">
                {citation.confidence !== undefined
                  ? `${(citation.confidence * 100).toFixed(1)}%`
                  : "Grounding Match"}
              </span>
            </div>

            <div className="p-3 rounded-[var(--radius-lg)] bg-[var(--bg-tertiary)]/40 border border-[var(--border-subtle)]">
              <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider block mb-1">
                Verification
              </span>
              <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
                <ShieldCheck size={14} />
                <span>{citation.entailment_status || "Entailed"}</span>
              </div>
            </div>
          </div>

          {/* Chunk Identifier */}
          <div className="p-3.5 rounded-[var(--radius-lg)] bg-[var(--bg-tertiary)]/30 border border-[var(--border-subtle)] flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider flex items-center gap-1.5">
                <Database size={12} />
                Chunk Reference
              </span>
              <button
                onClick={handleCopyChunkId}
                className="flex items-center gap-1 text-[11px] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors cursor-pointer"
              >
                {copied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                <span>{copied ? "Copied" : "Copy ID"}</span>
              </button>
            </div>
            <code className="text-[11px] font-mono text-[var(--text-secondary)] break-all bg-[var(--bg-elevated)] p-2 rounded-[var(--radius-sm)] border border-[var(--border-subtle)]">
              {citation.chunk_id}
            </code>
            <div className="text-[11px] text-[var(--text-muted)]">
              Sequence index in document: <span className="font-semibold text-[var(--text-secondary)]">#{citation.chunk_index + 1}</span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-[var(--border-subtle)] bg-[var(--bg-tertiary)]/30 flex items-center justify-between gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={handleOpenDocument}
            className="flex-1 gap-1.5 text-xs"
          >
            <ExternalLink size={13} />
            <span>Open in Library</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="text-xs"
          >
            Close
          </Button>
        </div>
      </aside>
    </>
  );
};

export default CitationDrawer;
