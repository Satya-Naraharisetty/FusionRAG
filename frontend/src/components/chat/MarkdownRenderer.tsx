import React, { useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { CodeBlock } from "./CodeBlock";
import { Download, Check } from "lucide-react";

interface MarkdownRendererProps {
  content: string;
}

const TableWrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const tableRef = useRef<HTMLDivElement>(null);
  const [downloaded, setDownloaded] = useState(false);

  const handleDownloadCSV = () => {
    if (!tableRef.current) return;
    const table = tableRef.current.querySelector("table");
    if (!table) return;

    const rows = Array.from(table.querySelectorAll("tr"));
    const csvContent = rows
      .map((row) => {
        const cells = Array.from(row.querySelectorAll("th, td"));
        return cells
          .map((cell) => {
            const text = cell.textContent?.replace(/"/g, '""').trim() || "";
            return `"${text}"`;
          })
          .join(",");
      })
      .join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `table_export_${Date.now()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    setDownloaded(true);
    setTimeout(() => setDownloaded(false), 2000);
  };

  return (
    <div
      ref={tableRef}
      className="my-3 group/table relative overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] shadow-sm"
    >
      <div className="flex items-center justify-between px-3 py-1.5 bg-[var(--bg-tertiary)]/70 border-b border-[var(--border-subtle)] text-[10px] text-[var(--text-muted)]">
        <span className="font-medium">Table</span>
        <button
          onClick={handleDownloadCSV}
          className="flex items-center gap-1 hover:text-[var(--text-primary)] transition-colors cursor-pointer"
          title="Download as CSV"
        >
          {downloaded ? (
            <>
              <Check size={11} className="text-emerald-400" />
              <span className="text-[10px] text-emerald-400">Exported</span>
            </>
          ) : (
            <>
              <Download size={11} />
              <span>Export CSV</span>
            </>
          )}
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-[var(--border-subtle)] text-[12px]">
          {children}
        </table>
      </div>
    </div>
  );
};

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content }) => {
  return (
    <div className="markdown-body max-w-none select-text text-[14px] leading-relaxed text-[var(--text-primary)] prose prose-invert">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || "");
            const isInline = !match && !String(children).includes("\n");

            return !isInline ? (
              <CodeBlock
                code={String(children).replace(/\n$/, "")}
                language={match ? match[1] : "text"}
              />
            ) : (
              <code
                className="rounded-[var(--radius-sm)] border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] px-1.5 py-0.5 font-mono text-[12px] text-[var(--accent-secondary)]"
                {...props}
              >
                {children}
              </code>
            );
          },
          table({ children }) {
            return <TableWrapper>{children}</TableWrapper>;
          },
          th({ children }) {
            return (
              <th className="bg-[var(--bg-tertiary)]/80 px-3.5 py-2.5 text-left font-semibold text-[var(--text-primary)] border-b border-[var(--border-subtle)]">
                {children}
              </th>
            );
          },
          td({ children }) {
            return (
              <td className="border-t border-[var(--border-subtle)] px-3.5 py-2 text-[var(--text-secondary)]">
                {children}
              </td>
            );
          },
          blockquote({ children }) {
            return (
              <blockquote className="my-2.5 pl-3.5 border-l-2 border-[var(--accent-primary)]/60 text-[var(--text-secondary)] italic">
                {children}
              </blockquote>
            );
          },
          a({ href, children }) {
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-[var(--accent-primary)] underline hover:text-[var(--accent-primary)]/85"
              >
                {children}
              </a>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};
