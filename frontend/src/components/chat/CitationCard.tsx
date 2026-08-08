import React, { useState } from "react";
import { Citation } from "../../types";

interface CitationCardProps {
  citation: Citation;
  index: number;
}

export const CitationCard: React.FC<CitationCardProps> = ({ citation, index }) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      onClick={() => setExpanded(!expanded)}
      className="inline-flex flex-col gap-1 px-2.5 py-1.5 bg-[var(--bg-tertiary)]/50 hover:bg-[var(--bg-tertiary)] border border-[var(--border-default)] hover:border-[var(--border-hover)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] rounded-[var(--radius-lg)] text-[10px] transition-all duration-150 cursor-pointer select-none"
    >
      <div className="flex items-center gap-1.5 font-medium">
        <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-[var(--bg-elevated)] text-[8px] font-bold text-[var(--text-muted)] border border-[var(--border-subtle)]">
          {index + 1}
        </span>
        <span className="truncate max-w-[120px]">{citation.document_name}</span>
        <span className="text-[var(--text-muted)]">·</span>
        <span className="text-[var(--text-muted)]">Chunk {citation.chunk_index}</span>
      </div>
      {expanded && (
        <div className="mt-0.5 pt-1.5 border-t border-[var(--border-subtle)] text-[9px] text-[var(--text-muted)] flex flex-col gap-0.5 animate-in fade-in duration-150">
          <div><span className="font-semibold text-[var(--text-secondary)]">Doc:</span> {citation.document_name}</div>
          <div><span className="font-semibold text-[var(--text-secondary)]">Chunk ID:</span> {citation.chunk_id}</div>
          <div><span className="font-semibold text-[var(--text-secondary)]">Index:</span> {citation.chunk_index}</div>
        </div>
      )}
    </div>
  );
};
