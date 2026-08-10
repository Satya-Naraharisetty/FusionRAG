import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock } from "./CodeBlock";

interface MarkdownRendererProps {
  content: string;
}

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content }) => {
  return (
    <div className="markdown-body max-w-none select-text text-xs leading-relaxed text-[var(--text-secondary)] prose prose-invert">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
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
                className="rounded-[var(--radius-sm)] border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--text-primary)]"
                {...props}
              >
                {children}
              </code>
            );
          },
          table({ children }) {
            return (
              <div className="my-3 overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--border-subtle)]">
                <table className="min-w-full divide-y divide-[var(--border-subtle)] text-[11px]">{children}</table>
              </div>
            );
          },
          th({ children }) {
            return <th className="bg-[var(--bg-tertiary)] px-3 py-2 text-left font-semibold text-[var(--text-primary)]">{children}</th>;
          },
          td({ children }) {
            return <td className="border-t border-[var(--border-subtle)] px-3 py-2 text-[var(--text-secondary)]">{children}</td>;
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
