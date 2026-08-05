import React from "react";
import { FileText } from "lucide-react";
import { Citation } from "../../types";

interface CitationCardProps {
  citation: Citation;
  index: number;
}

export const CitationCard: React.FC<CitationCardProps> = ({ citation, index }) => {
  return (
    <div className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-zinc-900 border border-zinc-800 hover:border-zinc-700 text-zinc-300 hover:text-zinc-100 rounded-full text-[10px] font-semibold transition-all duration-200 cursor-default select-none shadow-sm">
      <FileText size={10} className="text-violet-400" />
      <span className="truncate max-w-[120px]">{citation.document_name}</span>
      <span className="text-zinc-500 font-normal">[{citation.chunk_index}]</span>
      <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-zinc-800 text-[8px] font-bold text-zinc-400">
        {index + 1}
      </span>
    </div>
  );
};
