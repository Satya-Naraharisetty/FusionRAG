import React, { useState } from "react";
import {
  Terminal,
  Image as ImageIcon,
  Download,
  Maximize2,
  X,
  AlertCircle,
  Clock,
  Sparkles,
  RefreshCw,
} from "lucide-react";
import { ExecutionResult } from "../../lib/pyodide/pyodideManager";

interface CodeInterpreterOutputProps {
  result: ExecutionResult | null;
  isRunning: boolean;
  statusText?: string;
  onRerun?: () => void;
}

export const CodeInterpreterOutput: React.FC<CodeInterpreterOutputProps> = ({
  result,
  isRunning,
  statusText,
  onRerun,
}) => {
  const [selectedImage, setSelectedImage] = useState<string | null>(null);

  if (!isRunning && !result) {
    return null;
  }

  const handleDownload = (imgUrl: string, idx: number) => {
    const a = document.createElement("a");
    a.href = imgUrl;
    a.download = `plot_${Date.now()}_${idx + 1}.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  return (
    <div className="mt-2.5 overflow-hidden rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)]/90 shadow-sm animate-fade-in font-sans text-xs">
      {/* Header bar */}
      <div className="flex items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--bg-tertiary)]/80 px-3 py-2 text-[10px] text-[var(--text-muted)]">
        <div className="flex items-center gap-1.5 font-medium">
          <Terminal size={12} className="text-[var(--accent-primary)]" />
          <span className="text-[var(--text-primary)]">Sandbox Output (WASM)</span>
        </div>

        <div className="flex items-center gap-2">
          {isRunning ? (
            <div className="flex items-center gap-1.5 text-amber-400 font-medium animate-pulse">
              <RefreshCw size={10} className="animate-spin" />
              <span>{statusText || "Running..."}</span>
            </div>
          ) : result ? (
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1 text-[var(--text-muted)]">
                <Clock size={10} />
                <span>{Math.round(result.executionTimeMs)}ms</span>
              </div>
              {result.success ? (
                <span className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-400 border border-emerald-500/20">
                  Completed
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] bg-rose-500/10 px-1.5 py-0.5 text-[9px] font-semibold text-rose-400 border border-rose-500/20">
                  Failed
                </span>
              )}
              {onRerun && (
                <button
                  onClick={onRerun}
                  title="Re-run in sandbox"
                  className="p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] rounded transition-colors cursor-pointer"
                >
                  <RefreshCw size={10} />
                </button>
              )}
            </div>
          ) : null}
        </div>
      </div>

      {/* Content body */}
      <div className="p-3 space-y-3">
        {/* Error message if any */}
        {result && !result.success && result.error && (
          <div className="rounded-[var(--radius-md)] border border-rose-500/20 bg-rose-500/10 p-2.5 text-xs text-rose-300">
            <div className="flex items-center gap-1.5 font-semibold mb-1 text-rose-400">
              <AlertCircle size={13} />
              <span>Execution Error</span>
            </div>
            <pre className="font-mono text-[11px] whitespace-pre-wrap leading-relaxed text-rose-200/90 overflow-x-auto">
              {result.error}
            </pre>
          </div>
        )}

        {/* Console / Stdout text */}
        {result && result.stdout && (
          <div className="space-y-1">
            <div className="text-[10px] uppercase font-semibold text-[var(--text-muted)] tracking-wider">
              Console Output
            </div>
            <pre className="rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-2.5 font-mono text-[11px] leading-relaxed text-[var(--text-primary)] overflow-x-auto max-h-[220px]">
              {result.stdout}
            </pre>
          </div>
        )}

        {/* Rendered Matplotlib / Seaborn Chart Plots */}
        {result && result.plots && result.plots.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-[10px] uppercase font-semibold text-[var(--text-muted)] tracking-wider">
              <div className="flex items-center gap-1">
                <ImageIcon size={11} className="text-[var(--accent-primary)]" />
                <span>Generated Visualizations ({result.plots.length})</span>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3">
              {result.plots.map((plotUrl, idx) => (
                <div
                  key={idx}
                  className="group relative rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-white p-2 shadow-sm transition-all hover:border-[var(--accent-primary)]/50"
                >
                  <img
                    src={plotUrl}
                    alt={`Generated plot ${idx + 1}`}
                    className="w-full h-auto rounded object-contain max-h-[380px] mx-auto cursor-pointer"
                    onClick={() => setSelectedImage(plotUrl)}
                  />

                  {/* Overlay buttons */}
                  <div className="absolute top-3 right-3 flex items-center gap-1.5 opacity-0 transition-opacity group-hover:opacity-100 bg-black/60 backdrop-blur-sm p-1 rounded-[var(--radius-md)]">
                    <button
                      onClick={() => setSelectedImage(plotUrl)}
                      className="p-1 text-white hover:text-amber-300 transition-colors"
                      title="Expand full screen"
                    >
                      <Maximize2 size={13} />
                    </button>
                    <button
                      onClick={() => handleDownload(plotUrl, idx)}
                      className="p-1 text-white hover:text-emerald-300 transition-colors"
                      title="Download image"
                    >
                      <Download size={13} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Loading state indicator */}
        {isRunning && !result && (
          <div className="flex flex-col items-center justify-center py-6 gap-2 text-center text-[var(--text-muted)]">
            <Sparkles size={18} className="animate-spin text-[var(--accent-primary)]" />
            <div className="text-xs font-medium text-[var(--text-secondary)]">
              {statusText || "Running Python sandbox in browser..."}
            </div>
            <div className="text-[10px] text-[var(--text-muted)]">
              Executed 100% locally via WebAssembly (zero server compute load)
            </div>
          </div>
        )}
      </div>

      {/* Fullscreen Image Modal */}
      {selectedImage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm p-4 animate-fade-in"
          onClick={() => setSelectedImage(null)}
        >
          <div
            className="relative max-w-4xl max-h-[90vh] bg-white rounded-[var(--radius-xl)] p-2 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setSelectedImage(null)}
              className="absolute -top-3 -right-3 p-1.5 rounded-full bg-neutral-900 text-white hover:bg-neutral-800 transition-colors shadow-lg"
            >
              <X size={16} />
            </button>
            <img
              src={selectedImage}
              alt="Fullscreen visualization"
              className="max-h-[82vh] w-auto rounded object-contain"
            />
          </div>
        </div>
      )}
    </div>
  );
};
