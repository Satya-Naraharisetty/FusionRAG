import React from "react";
import { WifiOff, RefreshCcw, Play, X } from "lucide-react";
import { Button } from "../ui/Button";

interface StreamingRecoveryProps {
  onRetry: () => void;
  onContinue: () => void;
  onCancel: () => void;
  hasPartialContent?: boolean;
}

export const StreamingRecovery: React.FC<StreamingRecoveryProps> = ({
  onRetry,
  onContinue,
  onCancel,
  hasPartialContent = true,
}) => {
  return (
    <div className="my-4 flex max-w-lg flex-col gap-3 rounded-[var(--radius-xl)] border border-[var(--accent-error)]/20 bg-[var(--bg-secondary)] p-4 text-[var(--text-secondary)] animate-in fade-in duration-300">
      <div className="flex items-center gap-2.5 text-xs font-semibold text-[var(--accent-error)]">
        <WifiOff size={16} />
        <span>Connection lost during generation.</span>
      </div>
      <p className="text-[11px] text-[var(--text-muted)]">
        {hasPartialContent
          ? "The response stream was interrupted. You can choose to regenerate the response, continue from where it stopped, or cancel and keep the current partial text."
          : "The connection was interrupted before a response could be generated. Please retry or dismiss this notification."}
      </p>
      <div className="flex flex-wrap gap-2 mt-1">
        <Button onClick={onRetry} variant="outline" size="sm" className="h-8 gap-1.5 text-[10px]">
          <RefreshCcw size={12} />
          <span>Regenerate</span>
        </Button>
        {hasPartialContent && (
          <Button
            onClick={onContinue}
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 text-[10px]"
          >
            <Play size={12} />
            <span>Continue Writing</span>
          </Button>
        )}
        <Button onClick={onCancel} variant="ghost" size="sm" className="h-8 gap-1.5 text-[10px]">
          <X size={12} />
          <span>{hasPartialContent ? "Cancel & Keep" : "Dismiss"}</span>
        </Button>
      </div>
    </div>
  );
};
