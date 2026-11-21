import React from "react";
import { ArrowRight, GitBranch, Layers, Lock, ShieldCheck, Sparkles } from "lucide-react";
import { useLocale } from "../../lib/messages";

interface EmptyChatProps {
  onSelectPrompt: (prompt: string) => void;
}

export const EmptyChat: React.FC<EmptyChatProps> = ({ onSelectPrompt }) => {
  const { t } = useLocale();

  const examples = [
    { label: t("chat.example1"), prompt: t("chat.example1Prompt"), icon: "📄", tag: "Synthesis" },
    { label: t("chat.example2"), prompt: t("chat.example2Prompt"), icon: "💡", tag: "Hybrid RAG" },
    { label: t("chat.example3"), prompt: t("chat.example3Prompt"), icon: "🔍", tag: "Deep Search" },
    { label: t("chat.example4"), prompt: t("chat.example4Prompt"), icon: "⚖️", tag: "Comparison" },
  ];

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 pb-8 select-none relative">
      {/* Subtle ambient background glow */}
      <div className="pointer-events-none absolute h-72 w-72 rounded-full bg-[radial-gradient(circle_at_center,rgba(0,210,253,0.08)_0%,transparent_70%)] blur-2xl"></div>

      <div className="w-full max-w-[620px] flex flex-col items-center text-center relative z-10">
        {/* Brand Icon Badge with Gradient and Glow */}
        <div className="animate-fade-in-up mb-5 flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-[var(--radius-xl)] bg-[image:var(--gradient-main)] text-white shadow-[var(--shadow-glow)] transition-transform duration-200 hover:scale-105">
          <Sparkles className="h-7 w-7 text-white stroke-[2.2]" aria-hidden="true" />
        </div>

        {/* Heading */}
        <h2 className="animate-fade-in-up stagger-1 text-[30px] font-bold tracking-tight text-[var(--text-primary)] font-title leading-tight mb-2.5">
          {t("chat.emptyHeading")}
        </h2>

        {/* Supporting text */}
        <p className="animate-fade-in-up stagger-2 text-[14.5px] leading-relaxed text-[var(--text-secondary)] max-w-[480px] mb-6">
          {t("chat.emptySub")}
        </p>

        {/* Engine Capability Indicators (tasteskill: real engineering details) */}
        <div className="animate-fade-in-up stagger-3 flex flex-wrap items-center justify-center gap-2 mb-8">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-1 text-[11px] font-semibold text-[var(--accent-secondary)]">
            <GitBranch size={11} className="text-[var(--accent-primary)]" />
            7-Agent DAG Wave
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-1 text-[11px] font-semibold text-[var(--accent-secondary)]">
            <Layers size={11} className="text-[var(--accent-primary)]" />
            4-Stage Hybrid Fusion
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-1 text-[11px] font-semibold text-[var(--accent-secondary)]">
            <ShieldCheck size={11} className="text-[var(--accent-primary)]" />
            Verified Citations
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-1 text-[11px] font-semibold text-[var(--accent-secondary)]">
            <Lock size={11} className="text-[var(--accent-primary)]" />
            AES-256-GCM Encrypted
          </span>
        </div>

        {/* Prompt Recommendation Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full">
          {examples.map((item, idx) => (
            <button
              key={idx}
              onClick={() => onSelectPrompt(item.prompt)}
              className={`animate-fade-in-up stagger-${idx + 4} group flex items-start gap-3.5 p-4 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-xl)] cursor-pointer text-left transition-all duration-150 hover:-translate-y-0.5 hover:bg-[var(--bg-tertiary)] hover:border-[var(--border-cyan)] hover:shadow-[var(--elevation-3)] min-h-[64px]`}
              aria-label={item.label}
            >
              <span className="text-lg flex-shrink-0 leading-none pt-0.5">{item.icon}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-sm font-semibold text-[var(--text-primary)] leading-snug group-hover:text-white">
                    {item.label}
                  </span>
                  <span className="text-[10px] font-mono text-[var(--text-muted)] bg-[var(--bg-primary)] px-1.5 py-0.5 rounded border border-[var(--border-subtle)] flex-shrink-0">
                    {item.tag}
                  </span>
                </div>
                <p className="text-xs text-[var(--text-secondary)] line-clamp-1 leading-normal">
                  {item.prompt}
                </p>
              </div>
              <ArrowRight
                size={14}
                className="flex-shrink-0 text-[var(--accent-primary)] opacity-0 -translate-x-1 transition-all duration-150 group-hover:opacity-100 group-hover:translate-x-0 mt-1"
                aria-hidden="true"
              />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
