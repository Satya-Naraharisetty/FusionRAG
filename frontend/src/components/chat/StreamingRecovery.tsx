import React from "react";
import { WifiOff, RefreshCcw, Play, X } from "lucide-react";
import { Button } from "../ui/Button";

interface StreamingRecoveryProps {
  onRetry: () => void;
  onContinue: () => void;
  onCancel: () => void;
}

export const StreamingRecovery: React.FC<StreamingRecoveryProps> = ({
  onRetry,
  onContinue,
  onCancel,
}) => {
  return (
    <div className="flex flex-col gap-3 p-4 bg-red-950/20 border border-red-900/30 rounded-lg text-zinc-300 max-w-lg my-4 animate-in fade-in duration-300">
      <div className="flex items-center gap-2.5 text-red-400 font-semibold text-xs">
        <WifiOff size={16} />
        <span>Connection lost during generation.</span>
      </div>
      <p className="text-[11px] text-zinc-400">
        The response stream was interrupted. You can choose to regenerate the response, continue from where it stopped, or cancel and keep the current partial text.
      </p>
      <div className="flex flex-wrap gap-2 mt-1">
        <Button
          onClick={onRetry}
          variant="outline"
          size="sm"
          className="bg-zinc-900 border-zinc-800 hover:bg-zinc-800 text-zinc-300 text-[10px] h-8 gap-1.5"
        >
          <RefreshCcw size={12} />
          <span>Regenerate</span>
        </Button>
        <Button
          onClick={onContinue}
          variant="outline"
          size="sm"
          className="bg-zinc-900 border-zinc-800 hover:bg-zinc-800 text-zinc-300 text-[10px] h-8 gap-1.5"
        >
          <Play size={12} />
          <span>Continue Writing</span>
        </Button>
        <Button
          onClick={onCancel}
          variant="ghost"
          size="sm"
          className="hover:bg-zinc-900 text-zinc-400 hover:text-zinc-200 text-[10px] h-8 gap-1.5"
        >
          <X size={12} />
          <span>Cancel & Keep</span>
        </Button>
      </div>
    </div>
  );
};
