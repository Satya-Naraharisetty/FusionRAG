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
      className="inline-flex flex-col gap-1 px-3 py-1.5 bg-zinc-900/30 hover:bg-zinc-900/60 border border-[var(--border-color)] hover:border-[var(--border-hover)] text-zinc-300 hover:text-zinc-100 rounded-xl text-[10px] transition-all duration-200 cursor-pointer select-none shadow-xs"
    >
      <div className="flex items-center gap-1.5 font-medium">
        <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-zinc-900 text-[8px] font-bold text-zinc-400 border border-[var(--border-color)]">
          {index + 1}
        </span>
        <span className="truncate max-w-[120px]">{citation.document_name}</span>
        <span className="text-zinc-500 font-normal">·</span>
        <span className="text-zinc-500 font-normal">Chunk {citation.chunk_index}</span>
      </div>
      {expanded && (
        <div className="mt-1 pt-1 border-t border-[var(--border-color)] text-[9px] text-zinc-500 flex flex-col gap-0.5 animate-in fade-in duration-150">
          <div><span className="text-zinc-500 font-semibold">Doc Name:</span> {citation.document_name}</div>
          <div><span className="text-zinc-500 font-semibold">Chunk ID:</span> {citation.chunk_id}</div>
          <div><span className="text-zinc-500 font-semibold">Chunk Index:</span> {citation.chunk_index}</div>
        </div>
      )}
    </div>
  );
};
