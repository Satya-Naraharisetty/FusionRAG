import React, { useState, useEffect, useCallback } from "react";
import { Copy, Check, Play, Loader2 } from "lucide-react";
import { escapeHtml, highlightCode } from "../../lib/highlighter";
import { cn } from "../../lib/utils";
import { pyodideManager, ExecutionResult } from "../../lib/pyodide/pyodideManager";
import { CodeInterpreterOutput } from "./CodeInterpreterOutput";

interface CodeBlockProps {
  code: string;
  language: string;
}

export const CodeBlock: React.FC<CodeBlockProps> = ({ code, language }) => {
  const [html, setHtml] = useState("");
  const [copied, setCopied] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [statusText, setStatusText] = useState("");
  const [executionResult, setExecutionResult] = useState<ExecutionResult | null>(null);

  const isPython =
    language.toLowerCase() === "python" ||
    language.toLowerCase() === "py" ||
    (language === "" && (code.includes("import pandas") || code.includes("import matplotlib") || code.includes("import numpy") || code.includes("plt.")));

  useEffect(() => {
    let active = true;
    async function highlight() {
      try {
        const out = await highlightCode(code, language || (isPython ? "python" : "text"));
        if (active) setHtml(out);
      } catch {
        // highlightCode falls back internally; this guards against unforeseen failures.
        if (active) setHtml(`<pre class="shiki" tabindex="0"><code>${escapeHtml(code)}</code></pre>`);
      }
    }
    highlight();
    return () => {
      active = false;
    };
  }, [code, language, isPython]);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRun = useCallback(async () => {
    if (isRunning) return;
    setIsRunning(true);
    setStatusText("Initializing WebAssembly sandbox...");
    setExecutionResult(null);

    try {
      const res = await pyodideManager.runCode(code, undefined, (status) => {
        setStatusText(status);
      });
      setExecutionResult(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to execute in Pyodide sandbox.";
      setExecutionResult({
        success: false,
        stdout: "",
        plots: [],
        executionTimeMs: 0,
        error: msg,
      });
    } finally {
      setIsRunning(false);
      setStatusText("");
    }
  }, [code, isRunning]);

  const lineCount = code.split("\n").length;

  return (
    <div className="my-3 font-sans">
      <div className="relative group overflow-hidden rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-elevated)]/80 font-mono text-[11px] shadow-sm">
        {/* Header bar */}
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--bg-tertiary)]/70 px-3.5 py-2 text-[9px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          <div className="flex items-center gap-2">
            <span>{language || (isPython ? "python" : "text")}</span>
            {isPython && (
              <span className="rounded bg-[var(--accent-primary)]/15 px-1.5 py-0.5 text-[8px] font-medium text-[var(--accent-primary)] lowercase">
                wasm sandbox
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {isPython && (
              <button
                onClick={handleRun}
                disabled={isRunning}
                className={cn(
                  "flex cursor-pointer items-center gap-1 rounded-[var(--radius-sm)] bg-[var(--accent-primary)]/20 px-2 py-0.5 text-[10px] font-medium text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/30 transition-all duration-200 border border-[var(--accent-primary)]/30",
                  isRunning && "opacity-70 cursor-not-allowed"
                )}
                title="Execute Python in Browser WebAssembly (0% Server Load)"
              >
                {isRunning ? (
                  <>
                    <Loader2 size={10} className="animate-spin" />
                    <span>Running...</span>
                  </>
                ) : (
                  <>
                    <Play size={10} className="fill-current" />
                    <span>Run in Sandbox</span>
                  </>
                )}
              </button>
            )}

            <button
              onClick={handleCopy}
              className="flex cursor-pointer items-center gap-1 text-[var(--text-muted)] opacity-0 transition-all duration-200 group-hover:opacity-100 hover:text-[var(--text-primary)]"
            >
              {copied ? (
                <>
                  <Check size={10} />
                  <span>Copied!</span>
                </>
              ) : (
                <>
                  <Copy size={10} />
                  <span>Copy</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Code Content */}
        <div className="p-3 overflow-x-auto max-h-[400px] leading-relaxed">
          {html ? (
            <div
              dangerouslySetInnerHTML={{ __html: html }}
              className={cn("shiki-wrapper", lineCount > 5 && "has-line-numbers")}
            />
          ) : (
            <pre>
              <code>{code}</code>
            </pre>
          )}
        </div>
      </div>

      {/* Sandboxed Output Card (Terminal Console + Plots) */}
      <CodeInterpreterOutput
        result={executionResult}
        isRunning={isRunning}
        statusText={statusText}
        onRerun={handleRun}
      />
    </div>
  );
};
