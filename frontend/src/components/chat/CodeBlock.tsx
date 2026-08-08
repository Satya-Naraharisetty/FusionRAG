import React, { useState, useEffect } from "react";
import { Copy, Check } from "lucide-react";
import { codeToHtml } from "shiki";
import { cn } from "../../lib/utils";

interface CodeBlockProps {
  code: string;
  language: string;
}

export const CodeBlock: React.FC<CodeBlockProps> = ({ code, language }) => {
  const [html, setHtml] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    async function highlight() {
      try {
        const out = await codeToHtml(code, {
          lang: language || "text",
          theme: "github-dark",
        });
        if (active) setHtml(out);
      } catch (_e) {
        if (active) setHtml(`<pre class="shiki"><code>${escapeHtml(code)}</code></pre>`);
      }
    }
    highlight();
    return () => {
      active = false;
    };
  }, [code, language]);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const lineCount = code.split("\n").length;

  return (
    <div className="relative group my-3 border border-[var(--border-color)] rounded-xl overflow-hidden bg-zinc-950/30 font-mono text-[11px] shadow-sm">
      <div className="flex items-center justify-between px-3.5 py-2 bg-zinc-900/40 border-b border-[var(--border-color)] text-[9px] font-bold text-zinc-500 uppercase tracking-wide">
        <span>{language || "text"}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 hover:text-zinc-200 text-zinc-500 transition-all duration-200 opacity-0 group-hover:opacity-100 cursor-pointer"
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
  );
};

function escapeHtml(text: string) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

