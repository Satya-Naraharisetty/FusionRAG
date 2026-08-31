import React, { useState, useEffect } from "react";
import { X, ChevronLeft, ChevronRight, HelpCircle, Sparkles, FileText, Keyboard, MessageSquare } from "lucide-react";
import { Button } from "../ui/Button";

interface TooltipConfig {
  selector: string;
  label: string;
  icon: React.ReactNode;
  desc: string;
  fallback: { top: number; left: number; side: "left" | "top" };
}

const tooltipConfigs: TooltipConfig[] = [
  {
    selector: "#sidebar-new-chat-btn",
    label: "Create Chats",
    icon: <Sparkles size={13} className="text-[var(--accent-primary)]" />,
    desc: "Click here to start a fresh chat thread anytime.",
    fallback: { top: 60, left: 284, side: "left" },
  },
  {
    selector: "#sidebar-library-btn",
    label: "Document Library",
    icon: <FileText size={13} className="text-[var(--accent-primary)]" />,
    desc: "Upload files (PDF, DOCX, TXT, MD) to build and query your knowledge base.",
    fallback: { top: 100, left: 284, side: "left" },
  },
  {
    selector: "#sidebar-search-input",
    label: "Search & Shortcuts",
    icon: <Keyboard size={13} className="text-[var(--accent-primary)]" />,
    desc: "Quickly search past conversations or press Ctrl+K for the command palette.",
    fallback: { top: 180, left: 284, side: "left" },
  },
];

export const OnboardingTour: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [slideIdx, setSlideIdx] = useState(0);
  const [showTooltipStep, setShowTooltipStep] = useState<number | null>(null);
  const [tooltipLayout, setTooltipLayout] = useState<{
    top: number;
    left: number;
    arrowSide: "left" | "top";
    targetRect: { top: number; left: number; width: number; height: number } | null;
  } | null>(null);

  useEffect(() => {
    const completed = localStorage.getItem("onboarding-completed");
    if (!completed) setIsOpen(true);
  }, []);

  useEffect(() => {
    if (showTooltipStep === null) {
      setTooltipLayout(null);
      return;
    }

    const updatePosition = () => {
      const cfg = tooltipConfigs[showTooltipStep];
      if (!cfg) return;

      const el = document.querySelector(cfg.selector);
      if (el) {
        const rect = el.getBoundingClientRect();
        const tooltipWidth = 240;
        const tooltipHeight = 140;
        const spaceRight = window.innerWidth - rect.right;

        if (spaceRight >= tooltipWidth + 16) {
          // Position to the right of the target element
          const targetCenterY = rect.top + rect.height / 2;
          const top = Math.max(16, Math.min(targetCenterY - 36, window.innerHeight - tooltipHeight - 16));
          const left = rect.right + 12;
          setTooltipLayout({
            top,
            left,
            arrowSide: "left",
            targetRect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height },
          });
        } else {
          // Position below the target element
          const top = Math.min(rect.bottom + 10, window.innerHeight - tooltipHeight - 16);
          const left = Math.max(16, Math.min(rect.left, window.innerWidth - tooltipWidth - 16));
          setTooltipLayout({
            top,
            left,
            arrowSide: "top",
            targetRect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height },
          });
        }
      } else {
        // Sane fallback
        setTooltipLayout({
          top: cfg.fallback.top,
          left: cfg.fallback.left,
          arrowSide: cfg.fallback.side,
          targetRect: null,
        });
      }
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);

    const timer = setTimeout(updatePosition, 50);

    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
      clearTimeout(timer);
    };
  }, [showTooltipStep]);

  const handleNext = () => {
    if (slideIdx < 3) setSlideIdx(slideIdx + 1);
    else {
      setIsOpen(false);
      setShowTooltipStep(0);
    }
  };

  const handlePrev = () => {
    if (slideIdx > 0) setSlideIdx(slideIdx - 1);
  };

  const handleSkip = () => {
    setIsOpen(false);
    setShowTooltipStep(null);
    localStorage.setItem("onboarding-completed", "true");
    showCompletionToast();
  };

  const handlePrevTooltip = () => {
    if (showTooltipStep !== null && showTooltipStep > 0) {
      setShowTooltipStep(showTooltipStep - 1);
    }
  };

  const handleNextTooltip = () => {
    if (showTooltipStep !== null && showTooltipStep < tooltipConfigs.length - 1) {
      setShowTooltipStep(showTooltipStep + 1);
    } else {
      setShowTooltipStep(null);
      localStorage.setItem("onboarding-completed", "true");
      showCompletionToast();
    }
  };

  const showCompletionToast = () => {
    const el = document.createElement("div");
    el.className =
      "fixed bottom-6 right-6 z-50 bg-[var(--bg-elevated)] border border-[var(--border-default)] text-[var(--text-primary)] text-xs font-medium px-4 py-3 rounded-[var(--radius-xl)] shadow-md flex items-center gap-2 animate-in slide-in-from-bottom duration-300";
    el.innerHTML = `<span class="text-emerald-400">✨</span> Onboarding complete! Feel free to start chatting.`;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 4000);
  };

  /* Shared kbd style */
  const kbd =
    "bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] px-1 py-0.5 rounded text-[var(--text-muted)] text-[10px] font-mono";

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
                  <h3 className="text-base font-semibold text-[var(--text-primary)] font-title">Welcome to FusionRAG</h3>
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
                    Upload PDF, TXT, DOCX, MD, and image files. Chunks are extracted, vectorized, and retrieved automatically when you ask questions.
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

      {/* ── Spotlight on active element ── */}
      {showTooltipStep !== null && tooltipLayout?.targetRect && (
        <div
          style={{
            top: tooltipLayout.targetRect.top - 3,
            left: tooltipLayout.targetRect.left - 3,
            width: tooltipLayout.targetRect.width + 6,
            height: tooltipLayout.targetRect.height + 6,
          }}
          className="fixed z-40 pointer-events-none rounded-[var(--radius-lg)] border-2 border-[var(--accent-primary)] ring-4 ring-[var(--accent-primary)]/20 animate-pulse transition-all duration-200"
        />
      )}

      {/* ── Tooltip step card ── */}
      {showTooltipStep !== null && tooltipLayout && (
        <div
          style={{
            top: `${tooltipLayout.top}px`,
            left: `${tooltipLayout.left}px`,
          }}
          className="fixed z-50 w-[240px] bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-[var(--radius-xl)] p-3.5 shadow-xl animate-in fade-in zoom-in-95 duration-200 transition-all"
        >
          {/* Arrow pointer */}
          {tooltipLayout.arrowSide === "left" && (
            <div className="absolute left-[-5px] top-6 w-2.5 h-2.5 rotate-45 bg-[var(--bg-elevated)] border-l border-b border-[var(--border-default)]" />
          )}
          {tooltipLayout.arrowSide === "top" && (
            <div className="absolute top-[-5px] left-6 w-2.5 h-2.5 rotate-45 bg-[var(--bg-elevated)] border-t border-l border-[var(--border-default)]" />
          )}

          {/* Header */}
          <div className="flex items-center justify-between mb-1.5">
            <h4 className="text-xs font-semibold text-[var(--text-primary)] flex items-center gap-1.5">
              {tooltipConfigs[showTooltipStep].icon} {tooltipConfigs[showTooltipStep].label}
            </h4>
            <span className="text-[9px] font-mono text-[var(--text-muted)] bg-[var(--bg-tertiary)] px-1.5 py-0.5 rounded">
              {showTooltipStep + 1}/{tooltipConfigs.length}
            </span>
          </div>

          <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed mb-3">
            {tooltipConfigs[showTooltipStep].desc}
          </p>

          {/* Controls */}
          <div className="flex items-center gap-1.5">
            {showTooltipStep > 0 && (
              <Button
                variant="secondary"
                size="sm"
                onClick={handlePrevTooltip}
                className="h-7 text-[10px] px-2"
              >
                Back
              </Button>
            )}
            <Button
              size="sm"
              onClick={handleNextTooltip}
              fullWidth
              className="h-7 text-[10px]"
            >
              {showTooltipStep === tooltipConfigs.length - 1 ? "Finish Tour" : "Got it"}
            </Button>
          </div>
        </div>
      )}
    </>
  );
};

