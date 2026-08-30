import React from "react";
import {
  X,
  FileText,
  ExternalLink,
  Check,
  Copy,
  ShieldCheck,
  Globe,
  Quote,
  BookOpen,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
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
  const [showTechnicalDetails, setShowTechnicalDetails] = React.useState(false);

  if (!isOpen || !citation) return null;

  const isWeb = Boolean(
    citation.url ||
    citation.document_name.startsWith("[Web]") ||
    citation.document_name.toLowerCase().startsWith("http")
  );

  const cleanDocName = citation.document_name.replace(/^\[Web\]\s*/i, "");

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
            <div
              className={`h-8 w-8 rounded-[var(--radius-md)] border flex items-center justify-center flex-shrink-0 ${
                isWeb
                  ? "bg-sky-500/10 border-sky-500/20 text-sky-400"
                  : "bg-[var(--accent-primary)]/10 border-[var(--accent-primary)]/20 text-[var(--accent-primary)]"
              }`}
            >
              {isWeb ? <Globe size={16} /> : <FileText size={16} />}
            </div>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-[var(--text-primary)] truncate">
                {isWeb ? "Web Source Citation" : "Document Citation"}
              </h2>
              <p className="text-[11px] text-[var(--text-muted)] truncate">
                {cleanDocName}
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
          {/* Main Source Info Card */}
          <div className="p-3.5 rounded-[var(--radius-lg)] bg-[var(--bg-tertiary)]/40 border border-[var(--border-subtle)] flex flex-col gap-2.5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider flex items-center gap-1.5">
                {isWeb ? <Globe size={13} className="text-sky-400" /> : <BookOpen size={13} />}
                {isWeb ? "Web Resource" : "Document Info"}
              </span>
              {!isWeb && <FileTypeBadge filename={citation.document_name} />}
            </div>

            <div className="text-sm font-semibold text-[var(--text-primary)] break-words leading-snug">
              {cleanDocName}
            </div>

            {/* If it's a web source: Display the clickable source link */}
            {isWeb && citation.url && (
              <div className="pt-1">
                <a
                  href={citation.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-[var(--radius-md)] bg-sky-500/10 hover:bg-sky-500/20 border border-sky-500/20 text-sky-400 hover:text-sky-300 text-xs font-medium transition-colors break-all group w-full"
                >
                  <ExternalLink size={13} className="flex-shrink-0 group-hover:translate-x-0.5 transition-transform" />
                  <span className="truncate">{citation.url}</span>
                </a>
              </div>
            )}

            {/* Location in document (Page / Line / Section) */}
            {!isWeb && (
              <div className="flex flex-wrap items-center gap-1.5 pt-1 text-[11px]">
                {citation.page_number ? (
                  <span className="px-2 py-0.5 rounded-[var(--radius-sm)] bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-secondary)] font-medium">
                    Page {citation.page_number}
                  </span>
                ) : null}
                {citation.line_number ? (
                  <span className="px-2 py-0.5 rounded-[var(--radius-sm)] bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-secondary)] font-medium">
                    Line {citation.line_number}
                  </span>
                ) : null}
                <span className="px-2 py-0.5 rounded-[var(--radius-sm)] bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-muted)]">
                  Section #{citation.chunk_index + 1}
                </span>
                {citation.version !== undefined && (
                  <span className="px-2 py-0.5 rounded-[var(--radius-sm)] bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-muted)]">
                    v{citation.version}
                  </span>
                )}
                {citation.element_type && (
                  <span className="px-2 py-0.5 rounded-[var(--radius-sm)] bg-blue-500/10 border border-blue-500/20 text-blue-400 font-medium">
                    {citation.element_type}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Cited Content Snippet */}
          {citation.content && (
            <div className="p-3.5 rounded-[var(--radius-lg)] bg-[var(--bg-tertiary)]/30 border border-[var(--border-subtle)] flex flex-col gap-2">
              <span className="text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider flex items-center gap-1.5">
                <Quote size={12} />
                Cited Excerpt
              </span>
              <div className="text-xs text-[var(--text-secondary)] leading-relaxed italic bg-[var(--bg-elevated)] p-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] max-h-48 overflow-y-auto whitespace-pre-wrap">
                "{citation.content.trim()}"
              </div>
            </div>
          )}

          {/* Retrieval Confidence & Entailment Verification */}
          <div className="grid grid-cols-2 gap-2.5">
            <div className="p-3 rounded-[var(--radius-lg)] bg-[var(--bg-tertiary)]/40 border border-[var(--border-subtle)]">
              <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider block mb-1">
                Relevance Score
              </span>
              <span className="text-sm font-semibold text-[var(--accent-primary)] font-mono">
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

          {/* Collapsible Technical Reference */}
          <div className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] overflow-hidden">
            <button
              onClick={() => setShowTechnicalDetails(!showTechnicalDetails)}
              className="w-full px-3.5 py-2.5 bg-[var(--bg-tertiary)]/20 hover:bg-[var(--bg-tertiary)]/40 flex items-center justify-between text-[11px] text-[var(--text-muted)] transition-colors cursor-pointer"
            >
              <span>Technical Reference</span>
              {showTechnicalDetails ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>

            {showTechnicalDetails && (
              <div className="p-3.5 bg-[var(--bg-tertiary)]/10 border-t border-[var(--border-subtle)] flex flex-col gap-2 animate-in fade-in duration-150">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-[var(--text-muted)] font-mono">Chunk Reference</span>
                  <button
                    onClick={handleCopyChunkId}
                    className="flex items-center gap-1 text-[11px] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors cursor-pointer"
                  >
                    {copied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                    <span>{copied ? "Copied" : "Copy ID"}</span>
                  </button>
                </div>
                <code className="text-[10px] font-mono text-[var(--text-secondary)] break-all bg-[var(--bg-elevated)] p-2 rounded-[var(--radius-sm)] border border-[var(--border-subtle)]">
                  {citation.chunk_id}
                </code>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-[var(--border-subtle)] bg-[var(--bg-tertiary)]/30 flex items-center justify-between gap-3">
          {isWeb && citation.url ? (
            <a
              href={citation.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-[var(--radius-md)] bg-sky-500/15 hover:bg-sky-500/25 border border-sky-500/30 text-sky-400 hover:text-sky-300 font-medium text-xs transition-colors"
            >
              <ExternalLink size={13} />
              <span>Visit Source Webpage</span>
            </a>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={handleOpenDocument}
              className="flex-1 gap-1.5 text-xs"
            >
              <ExternalLink size={13} />
              <span>Open in Library</span>
            </Button>
          )}
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
