import React, { useState } from "react";
import { Globe, FileText } from "lucide-react";
import { Citation } from "../../types";

interface CitationCardProps {
  citation: Citation;
  index: number;
  onSelect?: (citation: Citation) => void;
}

export const CitationCard: React.FC<CitationCardProps> = ({ citation, index, onSelect }) => {
  const [expanded, setExpanded] = useState(false);

  const isWeb = Boolean(
    citation.url ||
    citation.document_name.startsWith("[Web]") ||
    citation.document_name.toLowerCase().startsWith("http")
  );

  const cleanDocName = citation.document_name.replace(/^\[Web\]\s*/i, "");

  const handleClick = (e: React.MouseEvent) => {
    if (onSelect) {
      e.stopPropagation();
      onSelect(citation);
    } else {
      setExpanded(!expanded);
    }
  };

  const getElementBadgeColor = (type?: string) => {
    switch (type) {
      case "TABLE":
        return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
      case "FIGURE":
        return "bg-purple-500/10 text-purple-400 border-purple-500/20";
      case "GRAPH_RELATIONSHIP":
        return "bg-amber-500/10 text-amber-400 border-amber-500/20";
      default:
        return "bg-blue-500/10 text-blue-400 border-blue-500/20";
    }
  };

  return (
    <div
      onClick={handleClick}
      className="inline-flex flex-col gap-1 px-2.5 py-1.5 bg-[var(--bg-tertiary)]/50 hover:bg-[var(--bg-tertiary)] border border-[var(--border-default)] hover:border-[var(--accent-primary)]/40 text-[var(--text-secondary)] hover:text-[var(--text-primary)] rounded-[var(--radius-lg)] text-[10px] transition-all duration-150 cursor-pointer select-none group"
    >
      <div className="flex items-center gap-1.5 font-medium">
        <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-[var(--bg-elevated)] text-[8px] font-bold text-[var(--text-muted)] border border-[var(--border-subtle)]">
          {index + 1}
        </span>
        {isWeb ? (
          <Globe size={11} className="text-sky-400 flex-shrink-0" />
        ) : (
          <FileText size={11} className="text-[var(--accent-primary)] flex-shrink-0" />
        )}
        <span className="truncate max-w-[130px]">{cleanDocName}</span>
        {citation.page_number && (
          <span className="px-1 py-0.2 rounded text-[8px] bg-[var(--bg-elevated)] text-[var(--text-muted)] border border-[var(--border-subtle)]">
            p.{citation.page_number}
          </span>
        )}
        {citation.version !== undefined && !citation.page_number && (
          <span className="px-1 py-0.2 rounded text-[8px] bg-[var(--bg-elevated)] text-[var(--text-muted)] border border-[var(--border-subtle)]">
            v{citation.version}
          </span>
        )}
        {citation.element_type && (
          <span className={`px-1 py-0.2 rounded text-[8px] border ${getElementBadgeColor(citation.element_type)}`}>
            {citation.element_type === "GRAPH_RELATIONSHIP" ? "GRAPH" : citation.element_type}
          </span>
        )}
        {citation.entailment_status === "ENTAILED" && (
          <span className="text-emerald-400 text-[9px] font-bold" title="Verified by Citation Entailment Gate">✓</span>
        )}
      </div>
      {expanded && (
        <div className="mt-0.5 pt-1.5 border-t border-[var(--border-subtle)] text-[9px] text-[var(--text-muted)] flex flex-col gap-0.5 animate-in fade-in duration-150">
          <div><span className="font-semibold text-[var(--text-secondary)]">Source:</span> {cleanDocName}</div>
          {citation.url && <div><span className="font-semibold text-[var(--text-secondary)]">URL:</span> {citation.url}</div>}
          {citation.page_number && <div><span className="font-semibold text-[var(--text-secondary)]">Page:</span> {citation.page_number}</div>}
          {citation.line_number && <div><span className="font-semibold text-[var(--text-secondary)]">Line:</span> {citation.line_number}</div>}
          {citation.version !== undefined && <div><span className="font-semibold text-[var(--text-secondary)]">Version:</span> v{citation.version}</div>}
          {citation.element_type && <div><span className="font-semibold text-[var(--text-secondary)]">Element Type:</span> {citation.element_type}</div>}
          {citation.confidence !== undefined && <div><span className="font-semibold text-[var(--text-secondary)]">Confidence:</span> {(citation.confidence * 100).toFixed(1)}%</div>}
        </div>
      )}
    </div>
  );
};

export default CitationCard;
