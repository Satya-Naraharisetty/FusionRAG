import React from "react";
import { ArrowRight } from "lucide-react";

interface EmptyChatProps {
  onSelectPrompt: (prompt: string) => void;
}

const EXAMPLES = [
  { label: "Summarize my documents",    prompt: "Can you provide a comprehensive summary of my uploaded documents?",            icon: "📄" },
  { label: "Explain this concept",      prompt: "Explain how our retrieval pipeline merges vector and sparse results.",          icon: "💡" },
  { label: "Search my knowledge base",  prompt: "Find all key references to security policies inside the documents.",            icon: "🔍" },
  { label: "Compare these documents",   prompt: "Compare the architecture guidelines in file A and file B.",                     icon: "⚖️" },
];

export const EmptyChat: React.FC<EmptyChatProps> = ({ onSelectPrompt }) => {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 pb-8 select-none">
      <div className="w-full max-w-[580px] flex flex-col items-center text-center">

        {/* Logo badge — gradient tile with glow */}
        <div className="animate-fade-in-up mb-6 flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-[var(--radius-lg)] bg-[image:var(--gradient-main)] text-white shadow-[var(--shadow-glow)] transition-transform duration-200 hover:scale-105">
          <span className="font-title text-xl font-bold leading-none">H</span>
        </div>

        {/* Heading with gradient accent */}
        <h2 className="animate-fade-in-up stagger-1 text-[28px] font-semibold tracking-tight text-[var(--text-primary)] font-title leading-tight mb-3">
          How can I{" "}
          <span className="bg-[image:var(--gradient-main)] bg-clip-text text-transparent">
            help you
          </span>{" "}
          today?
        </h2>

        {/* Supporting text */}
        <p className="animate-fade-in-up stagger-2 text-[15px] leading-relaxed text-[var(--text-secondary)] max-w-[440px] mb-8">
          Upload PDF, TXT, DOCX, or MD files to your library, then ask questions to retrieve grounded insights.
        </p>

        {/* Prompt grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full">
          {EXAMPLES.map((item, idx) => (
            <button
              key={idx}
              onClick={() => onSelectPrompt(item.prompt)}
              className={`animate-fade-in-up stagger-${idx + 3} group flex items-center gap-3 px-4 py-3.5 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-xl)] cursor-pointer text-left transition-all duration-150 hover:-translate-y-0.5 hover:bg-[var(--bg-tertiary)] hover:border-[var(--border-hover)] hover:shadow-[var(--elevation-3)] min-h-[52px]`}
              aria-label={item.label}
            >
              <span className="text-base flex-shrink-0 leading-none">{item.icon}</span>
              <span className="flex-1 text-sm font-medium text-[var(--text-primary)] leading-snug">
                {item.label}
              </span>
              <ArrowRight
                size={14}
                className="flex-shrink-0 text-[var(--accent-primary)] opacity-0 -translate-x-1 transition-all duration-150 group-hover:opacity-100 group-hover:translate-x-0"
                aria-hidden="true"
              />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
