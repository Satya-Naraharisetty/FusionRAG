import React, { useState } from "react";
import { Terminal, Check, AlertCircle, ChevronDown, ChevronUp } from "lucide-react";
import { ToolCallEvent } from "../../types";
import { cn } from "../../lib/utils";

interface ToolCallCardProps {
  toolCall: ToolCallEvent;
}

export const ToolCallCard: React.FC<ToolCallCardProps> = ({ toolCall }) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-zinc-800/80 bg-zinc-950/40 rounded-lg text-xs w-full max-w-2xl my-2 overflow-hidden shadow-sm">
      {/* Header bar */}
      <div
        onClick={() => setExpanded(!expanded)}
        className="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-zinc-900/30 transition-all duration-200"
      >
        <div className="flex items-center gap-2">
          {toolCall.status === "running" ? (
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-violet-500 border-t-transparent" />
          ) : toolCall.status === "done" ? (
            <div className="flex h-4 w-4 items-center justify-center rounded-full bg-emerald-950/50 text-emerald-400">
              <Check size={10} />
            </div>
          ) : (
            <div className="flex h-4 w-4 items-center justify-center rounded-full bg-red-950/50 text-red-400">
              <AlertCircle size={10} />
            </div>
          )}
          <Terminal size={14} className="text-zinc-500" />
          <span className="font-semibold text-zinc-300">Tool: {toolCall.name}</span>
          <span
            className={cn(
              "text-[9px] px-1.5 py-0.5 rounded font-bold uppercase tracking-wider",
              toolCall.status === "running" && "bg-violet-950/55 text-violet-300",
              toolCall.status === "done" && "bg-emerald-950/55 text-emerald-300",
              toolCall.status === "failed" && "bg-red-950/55 text-red-300"
            )}
          >
            {toolCall.status}
          </span>
        </div>
        <div className="text-zinc-500">
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="p-3 border-t border-zinc-900 bg-zinc-950/80 font-mono text-[10px] text-zinc-400 flex flex-col gap-2.5">
          <div>
            <span className="text-zinc-500 block mb-1 font-semibold uppercase tracking-wide">Arguments:</span>
            <pre className="p-2 bg-zinc-900/60 rounded border border-zinc-800/40 overflow-x-auto">
              {JSON.stringify(toolCall.arguments, null, 2)}
            </pre>
          </div>
          {toolCall.result !== undefined && (
            <div>
              <span className="text-zinc-500 block mb-1 font-semibold uppercase tracking-wide">Result:</span>
              <pre className="p-2 bg-zinc-900/60 rounded border border-zinc-800/40 overflow-x-auto text-zinc-300">
                {typeof toolCall.result === "object"
                  ? JSON.stringify(toolCall.result, null, 2)
                  : String(toolCall.result)}
              </pre>
            </div>
          )}
          {toolCall.error && (
            <div>
              <span className="text-red-400 block mb-1 font-semibold uppercase tracking-wide">Error:</span>
              <pre className="p-2 bg-red-950/10 text-red-300 rounded border border-red-900/20 overflow-x-auto">
                {toolCall.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
