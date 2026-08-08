import React, { useState, useEffect } from "react";
import { X, ChevronLeft, ChevronRight, HelpCircle, Sparkles, FileText, Keyboard, MessageSquare } from "lucide-react";
import { Button } from "../ui/Button";

export const OnboardingTour: React.FC = () => {
  const [isOpen, setIsOpen]               = useState(false);
  const [slideIdx, setSlideIdx]           = useState(0);
  const [showTooltipStep, setShowTooltipStep] = useState<number | null>(null);

  useEffect(() => {
    const completed = localStorage.getItem("onboarding-completed");
    if (!completed) setIsOpen(true);
  }, []);

  const handleNext = () => {
    if (slideIdx < 3) setSlideIdx(slideIdx + 1);
    else { setIsOpen(false); setShowTooltipStep(0); }
  };

  const handlePrev = () => { if (slideIdx > 0) setSlideIdx(slideIdx - 1); };

  const handleSkip = () => {
    setIsOpen(false);
    setShowTooltipStep(null);
    localStorage.setItem("onboarding-completed", "true");
    showCompletionToast();
  };

  const handleNextTooltip = () => {
    if (showTooltipStep !== null && showTooltipStep < 2) {
      setShowTooltipStep(showTooltipStep + 1);
    } else {
      setShowTooltipStep(null);
      localStorage.setItem("onboarding-completed", "true");
      showCompletionToast();
    }
  };

  const showCompletionToast = () => {
    const el = document.createElement("div");
    el.className = "fixed bottom-6 right-6 z-50 bg-[var(--bg-elevated)] border border-[var(--border-default)] text-[var(--text-primary)] text-xs font-medium px-4 py-3 rounded-[var(--radius-xl)] shadow-md flex items-center gap-2 animate-in slide-in-from-bottom duration-300";
    el.innerHTML = `<span class="text-emerald-400">✨</span> Onboarding complete! Feel free to start chatting.`;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 4000);
  };

  /* Shared kbd style */
  const kbd = "bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] px-1 py-0.5 rounded text-[var(--text-muted)] text-[10px] font-mono";

  if (!isOpen && showTooltipStep === null) return null;

  return (
    <>
      {/* ── Modal carousel ── */}
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="relative w-full max-w-[480px] bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-[var(--radius-2xl)] p-6 shadow-md space-y-5 overflow-hidden mx-4">
            {/* Ambient glows */}
            <div className="absolute -top-10 -right-10 h-32 w-32 rounded-full bg-[var(--accent-primary)]/8 blur-3xl pointer-events-none" />
            <div className="absolute -bottom-10 -left-10 h-32 w-32 rounded-full bg-[var(--accent-secondary)]/8 blur-3xl pointer-events-none" />

            {/* Header */}
            <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-3 relative z-10 select-none">
              <span className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider flex items-center gap-1.5">
                <HelpCircle size={11} className="text-[var(--accent-primary)]" />
                Console Guide ({slideIdx + 1}/4)
              </span>
              <button
                onClick={handleSkip}
                className="text-[var(--text-muted)] hover:text-[var(--text-primary)] p-1 cursor-pointer transition-colors rounded"
                aria-label="Skip onboarding"
              >
                <X size={14} />
              </button>
            </div>

            {/* Slides */}
            <div className="relative min-h-[180px] flex flex-col justify-center text-center px-2 z-10">
              {slideIdx === 0 && (
                <div className="space-y-3 animate-in fade-in slide-in-from-right duration-300">
                  <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] border border-[var(--accent-primary)]/20">
                    <Sparkles size={18} />
                  </div>
                  <h3 className="text-base font-semibold text-[var(--text-primary)] font-title">Welcome to Hybrid RAG</h3>
                  <p className="text-xs text-[var(--text-secondary)] leading-relaxed max-w-sm mx-auto">
                    Ground your AI answers with precision using hybrid sparse + dense vector retrieval for verified, accurate responses.
                  </p>
                </div>
              )}
              {slideIdx === 1 && (
                <div className="space-y-3 animate-in fade-in slide-in-from-right duration-300">
                  <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                    <FileText size={18} />
                  </div>
                  <h3 className="text-base font-semibold text-[var(--text-primary)] font-title">Document Library</h3>
                  <p className="text-xs text-[var(--text-secondary)] leading-relaxed max-w-sm mx-auto">
                    Upload PDF, TXT, DOCX, MD files. Chunks are extracted, vectorized, and retrieved automatically when you ask questions.
                  </p>
                </div>
              )}
              {slideIdx === 2 && (
                <div className="space-y-3 animate-in fade-in slide-in-from-right duration-300">
                  <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-[var(--accent-secondary)]/10 text-[var(--accent-secondary)] border border-[var(--accent-secondary)]/20">
                    <MessageSquare size={18} />
                  </div>
                  <h3 className="text-base font-semibold text-[var(--text-primary)] font-title">Rich Chat Inputs</h3>
                  <p className="text-xs text-[var(--text-secondary)] leading-relaxed max-w-sm mx-auto">
                    Attach files, use voice prompts, or type slash commands like <code className="text-[var(--accent-primary)] bg-[var(--bg-tertiary)] px-1 py-0.5 rounded text-[10px]">/settings</code> inside the chat.
                  </p>
                </div>
              )}
              {slideIdx === 3 && (
                <div className="space-y-3 animate-in fade-in slide-in-from-right duration-300">
                  <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
                    <Keyboard size={18} />
                  </div>
                  <h3 className="text-base font-semibold text-[var(--text-primary)] font-title">Keyboard Navigation</h3>
                  <p className="text-xs text-[var(--text-secondary)] leading-relaxed max-w-sm mx-auto">
                    Navigate with <kbd className={kbd}>↑</kbd> <kbd className={kbd}>↓</kbd>, pin with <kbd className={kbd}>Ctrl+P</kbd>, and focus search with <kbd className={kbd}>/</kbd>.
                  </p>
                </div>
              )}
            </div>

            {/* Footer nav */}
            <div className="flex items-center justify-between border-t border-[var(--border-subtle)] pt-4 z-10 select-none">
              <div className="flex gap-1.5">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div
                    key={i}
                    className={`h-1.5 rounded-full transition-all duration-300 ${
                      i === slideIdx
                        ? "w-4 bg-[var(--accent-primary)]"
                        : "w-1.5 bg-[var(--bg-tertiary)]"
                    }`}
                  />
                ))}
              </div>
              <div className="flex gap-2">
                {slideIdx > 0 && (
                  <Button variant="secondary" size="sm" onClick={handlePrev} className="gap-1 h-8">
                    <ChevronLeft size={13} /> Back
                  </Button>
                )}
                <Button size="sm" onClick={handleNext} className="gap-1 h-8">
                  {slideIdx === 3 ? "Start Tour" : "Next"} <ChevronRight size={13} />
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Tooltip steps ── */}
      {[0, 1, 2].map((step) => {
        if (showTooltipStep !== step) return null;
        const configs = [
          { label: "Create Chats",        icon: <Sparkles size={12} className="text-[var(--accent-primary)]" />, desc: "Click here to start a new chat thread.", pos: "bottom-[74px] left-[70px]" },
          { label: "Upload Knowledge",    icon: <FileText size={12} className="text-[var(--accent-primary)]" />, desc: "Access the documents dashboard to upload files and build your knowledge base.", pos: "bottom-[32px] left-[70px]" },
          { label: "Keyboard Shortcuts",  icon: <Keyboard size={12} className="text-[var(--accent-primary)]" />, desc: "Use Ctrl+K for the command palette, Ctrl+N for new chat, and arrow keys to navigate.", pos: "bottom-[20px] left-[150px]" },
        ];
        const c = configs[step];
        return (
          <div
            key={step}
            className={`fixed ${c.pos} z-50 max-w-[220px] bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-[var(--radius-xl)] p-3 shadow-md animate-bounce`}
          >
            <div className="absolute left-[-5px] top-5 w-2.5 h-2.5 rotate-45 bg-[var(--bg-elevated)] border-l border-b border-[var(--border-default)]" />
            <h4 className="text-xs font-semibold text-[var(--text-primary)] mb-1 flex items-center gap-1.5">
              {c.icon} {c.label}
            </h4>
            <p className="text-[10px] text-[var(--text-muted)] leading-normal mb-2.5">{c.desc}</p>
            <Button size="sm" onClick={handleNextTooltip} fullWidth className="h-7 text-[10px]">
              {step === 2 ? "Finish Tour" : "Got it"}
            </Button>
          </div>
        );
      })}
    </>
  );
};
