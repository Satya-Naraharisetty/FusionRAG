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
    <div className="my-2 w-full max-w-2xl overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-xs shadow-sm">
      {/* Header bar */}
      <div
        onClick={() => setExpanded(!expanded)}
        className="flex cursor-pointer items-center justify-between px-3 py-2 transition-all duration-200 hover:bg-[var(--bg-tertiary)]/60"
      >
        <div className="flex items-center gap-2">
          {toolCall.status === "running" ? (
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-[var(--accent-primary)] border-t-transparent" />
          ) : toolCall.status === "done" ? (
            <div className="flex h-4 w-4 items-center justify-center rounded-full bg-[var(--accent-success)]/10 text-[var(--accent-success)]">
              <Check size={10} />
            </div>
          ) : (
            <div className="flex h-4 w-4 items-center justify-center rounded-full bg-[var(--accent-error)]/10 text-[var(--accent-error)]">
              <AlertCircle size={10} />
            </div>
          )}
          <Terminal size={14} className="text-[var(--text-muted)]" />
          <span className="font-semibold text-[var(--text-primary)]">Tool: {toolCall.name}</span>
          <span
            className={cn(
              "text-[9px] px-1.5 py-0.5 rounded font-bold uppercase tracking-wider",
              toolCall.status === "running" && "bg-[var(--accent-primary)]/12 text-[var(--accent-primary)]",
              toolCall.status === "done" && "bg-[var(--accent-success)]/12 text-[var(--accent-success)]",
              toolCall.status === "failed" && "bg-[var(--accent-error)]/12 text-[var(--accent-error)]"
            )}
          >
            {toolCall.status}
          </span>
        </div>
        <div className="text-[var(--text-muted)]">
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="flex flex-col gap-2.5 border-t border-[var(--border-subtle)] bg-[var(--bg-elevated)]/80 p-3 font-mono text-[10px] text-[var(--text-secondary)]">
          <div>
            <span className="mb-1 block font-semibold uppercase tracking-wide text-[var(--text-muted)]">Arguments:</span>
            <pre className="overflow-x-auto rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-tertiary)]/70 p-2">
              {JSON.stringify(toolCall.arguments, null, 2)}
            </pre>
          </div>
          {toolCall.result !== undefined && (
            <div>
              <span className="mb-1 block font-semibold uppercase tracking-wide text-[var(--text-muted)]">Result:</span>
              <pre className="overflow-x-auto rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-tertiary)]/70 p-2 text-[var(--text-primary)]">
                {typeof toolCall.result === "object"
                  ? JSON.stringify(toolCall.result, null, 2)
                  : String(toolCall.result)}
              </pre>
            </div>
          )}
          {toolCall.error && (
            <div>
              <span className="mb-1 block font-semibold uppercase tracking-wide text-[var(--accent-error)]">Error:</span>
              <pre className="overflow-x-auto rounded-[var(--radius-md)] border border-[var(--accent-error)]/20 bg-[var(--accent-error)]/8 p-2 text-[var(--accent-error)]">
                {toolCall.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
