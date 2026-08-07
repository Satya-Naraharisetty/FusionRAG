import React, { useState, useEffect } from "react";
import { X, ChevronLeft, ChevronRight, HelpCircle, Sparkles, FileText, Keyboard, MessageSquare } from "lucide-react";
import { Button } from "../ui/button";

export const OnboardingTour: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [slideIdx, setSlideIdx] = useState(0);
  const [showTooltipStep, setShowTooltipStep] = useState<number | null>(null);

  useEffect(() => {
    const completed = localStorage.getItem("onboarding-completed");
    if (!completed) {
      setIsOpen(true);
    }
  }, []);

  const handleNext = () => {
    if (slideIdx < 3) {
      setSlideIdx(slideIdx + 1);
    } else {
      // End slides, start interactive tooltips
      setIsOpen(false);
      setShowTooltipStep(0); // first tooltip step
    }
  };

  const handlePrev = () => {
    if (slideIdx > 0) {
      setSlideIdx(slideIdx - 1);
    }
  };

  const handleSkip = () => {
    setIsOpen(false);
    setShowTooltipStep(null);
    localStorage.setItem("onboarding-completed", "true");
    toastSuccess();
  };

  const handleNextTooltip = () => {
    if (showTooltipStep !== null && showTooltipStep < 2) {
      setShowTooltipStep(showTooltipStep + 1);
    } else {
      setShowTooltipStep(null);
      localStorage.setItem("onboarding-completed", "true");
      toastSuccess();
    }
  };

  const toastSuccess = () => {
    // Show premium completion notification
    const notification = document.createElement("div");
    notification.className = "fixed bottom-6 right-6 z-50 bg-zinc-900 border border-zinc-800 text-zinc-100 text-xs font-semibold px-4 py-3 rounded-xl shadow-2xl flex items-center gap-2 animate-in slide-in-from-bottom duration-300";
    notification.innerHTML = `<span class="text-emerald-400">✨</span> Onboarding complete! Feel free to ask queries.`;
    document.body.appendChild(notification);
    setTimeout(() => notification.remove(), 4000);
  };

  if (!isOpen && showTooltipStep === null) return null;

  return (
    <>
      {/* Modal Carousel Panel */}
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md animate-in fade-in duration-300">
          <div className="relative w-full max-w-[500px] bg-zinc-950 border border-zinc-850 rounded-2xl p-6.5 shadow-2xl space-y-6 overflow-hidden">
            {/* Dynamic decorative colors */}
            <div className="absolute -top-12 -right-12 h-36 w-36 rounded-full bg-violet-650/10 blur-2xl pointer-events-none" />
            <div className="absolute -bottom-12 -left-12 h-36 w-36 rounded-full bg-fuchsia-650/10 blur-2xl pointer-events-none" />

            {/* Header controls */}
            <div className="flex items-center justify-between border-b border-zinc-900 pb-3 relative z-10 select-none">
              <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest flex items-center gap-1.5">
                <HelpCircle size={12} className="text-violet-500" />
                <span>Console Guide ({slideIdx + 1}/4)</span>
              </span>
              <button
                onClick={handleSkip}
                className="text-zinc-500 hover:text-zinc-350 p-1 cursor-pointer transition-colors duration-200"
                aria-label="Skip onboarding"
              >
                <X size={15} />
              </button>
            </div>

            {/* Slides container */}
            <div className="relative min-h-[190px] flex flex-col justify-center text-center px-4 relative z-10">
              {slideIdx === 0 && (
                <div className="space-y-3 animate-in fade-in slide-in-from-right duration-350">
                  <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-violet-950/40 text-violet-400 border border-violet-900/30 shadow-md">
                    <Sparkles size={20} />
                  </div>
                  <h3 className="text-base font-bold font-title text-zinc-100">Welcome to Hybrid RAG Console</h3>
                  <p className="text-xs text-zinc-450 leading-relaxed max-w-sm mx-auto">
                    Ground your AI assistant answers with precision. By combining sparse keyword indexing and dense semantic vectors, your responses are verified and accurate.
                  </p>
                </div>
              )}

              {slideIdx === 1 && (
                <div className="space-y-3 animate-in fade-in slide-in-from-right duration-350">
                  <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-blue-950/40 text-blue-400 border border-blue-900/30 shadow-md">
                    <FileText size={20} />
                  </div>
                  <h3 className="text-base font-bold font-title text-zinc-100">Document Grounding Library</h3>
                  <p className="text-xs text-zinc-450 leading-relaxed max-w-sm mx-auto">
                    Upload documents (PDF, TXT, DOCX, MD) in the repository. Chunks are extracted, vectorized, and automatically retrieved when asking contextual queries.
                  </p>
                </div>
              )}

              {slideIdx === 2 && (
                <div className="space-y-3 animate-in fade-in slide-in-from-right duration-350">
                  <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-fuchsia-950/40 text-fuchsia-400 border border-fuchsia-900/30 shadow-md">
                    <MessageSquare size={20} />
                  </div>
                  <h3 className="text-base font-bold font-title text-zinc-100">Rich Conversational Inputs</h3>
                  <p className="text-xs text-zinc-450 leading-relaxed max-w-sm mx-auto">
                    Use attachments, dictate voice prompts, or type slash commands like <code className="text-violet-400 bg-zinc-900 px-1 py-0.5 rounded">/settings</code> directly inside the chat window.
                  </p>
                </div>
              )}

              {slideIdx === 3 && (
                <div className="space-y-3 animate-in fade-in slide-in-from-right duration-350">
                  <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-amber-950/40 text-amber-500 border border-amber-900/30 shadow-md">
                    <Keyboard size={20} />
                  </div>
                  <h3 className="text-base font-bold font-title text-zinc-100">Keyboard Navigation</h3>
                  <p className="text-xs text-zinc-450 leading-relaxed max-w-sm mx-auto">
                    Navigate list items via <kbd className="bg-zinc-900 border border-zinc-800 px-1 py-0.5 rounded">↑</kbd> <kbd className="bg-zinc-900 border border-zinc-800 px-1 py-0.5 rounded">↓</kbd>, pin with <kbd className="bg-zinc-900 border border-zinc-800 px-1 py-0.5 rounded">Ctrl+P</kbd>, and focus query search bar using the <kbd className="bg-zinc-900 border border-zinc-800 px-1.5 py-0.5 rounded">/</kbd> key.
                  </p>
                </div>
              )}
            </div>

            {/* Navigation footer */}
            <div className="flex items-center justify-between border-t border-zinc-900 pt-4 relative z-10 select-none">
              <div className="flex gap-1.5">
                {Array.from({ length: 4 }).map((_, idx) => (
                  <div
                    key={idx}
                    className={`h-1.5 rounded-full transition-all duration-300 ${
                      idx === slideIdx ? "w-4 bg-violet-600" : "w-1.5 bg-zinc-800"
                    }`}
                  />
                ))}
              </div>

              <div className="flex gap-2">
                {slideIdx > 0 && (
                  <Button
                    variant="outline"
                    onClick={handlePrev}
                    className="h-8.5 px-3.5 bg-zinc-900 border-zinc-850 hover:bg-zinc-850 text-zinc-400 text-xs font-semibold cursor-pointer gap-1"
                  >
                    <ChevronLeft size={14} />
                    <span>Back</span>
                  </Button>
                )}
                <Button
                  onClick={handleNext}
                  className="h-8.5 px-4.5 bg-violet-600 hover:bg-violet-750 text-white text-xs font-bold cursor-pointer gap-1"
                >
                  <span>{slideIdx === 3 ? "Launch Guide" : "Next"}</span>
                  <ChevronRight size={14} />
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Floating Tooltips step-by-step guides */}
      {showTooltipStep === 0 && (
        <div className="fixed bottom-[74px] left-[70px] z-50 max-w-[240px] bg-zinc-950 border border-zinc-800 rounded-xl p-3 shadow-2xl animate-bounce duration-1000">
          <div className="absolute left-[-6px] top-6 w-3 h-3 rotate-45 bg-zinc-950 border-l border-b border-zinc-800" />
          <h4 className="text-xs font-bold text-zinc-200 mb-1 flex items-center gap-1.5">
            <Sparkles size={13} className="text-violet-500 animate-pulse" />
            <span>Create Chats</span>
          </h4>
          <p className="text-[10px] text-zinc-400 leading-normal mb-2.5">
            Click here to start a new workspace chat thread and converse.
          </p>
          <Button onClick={handleNextTooltip} className="h-7 w-full text-[10px] bg-violet-650 hover:bg-violet-750 text-white font-bold cursor-pointer">
            Got it
          </Button>
        </div>
      )}

      {showTooltipStep === 1 && (
        <div className="fixed bottom-[32px] left-[70px] z-50 max-w-[240px] bg-zinc-950 border border-zinc-800 rounded-xl p-3 shadow-2xl animate-bounce duration-1000">
          <div className="absolute left-[-6px] top-6 w-3 h-3 rotate-45 bg-zinc-950 border-l border-b border-zinc-800" />
          <h4 className="text-xs font-bold text-zinc-200 mb-1 flex items-center gap-1.5">
            <FileText size={13} className="text-violet-500 animate-pulse" />
            <span>Upload Knowledge</span>
          </h4>
          <p className="text-[10px] text-zinc-400 leading-normal mb-2.5">
            Access documents dashboard here to drop files and build grounding search vectors.
          </p>
          <Button onClick={handleNextTooltip} className="h-7 w-full text-[10px] bg-violet-650 hover:bg-violet-750 text-white font-bold cursor-pointer">
            Got it
          </Button>
        </div>
      )}

      {showTooltipStep === 2 && (
        <div className="fixed bottom-[20px] left-[150px] z-50 max-w-[240px] bg-zinc-950 border border-zinc-800 rounded-xl p-3 shadow-2xl animate-bounce duration-1000">
          <div className="absolute left-[-6px] top-6 w-3 h-3 rotate-45 bg-zinc-950 border-l border-b border-zinc-800" />
          <h4 className="text-xs font-bold text-zinc-200 mb-1 flex items-center gap-1.5">
            <Keyboard size={13} className="text-violet-500 animate-pulse" />
            <span>Interactive Console</span>
          </h4>
          <p className="text-[10px] text-zinc-400 leading-normal mb-2.5">
            Hold control and key mappings to trigger options easily. Happy grounding!
          </p>
          <Button onClick={handleNextTooltip} className="h-7 w-full text-[10px] bg-violet-650 hover:bg-violet-750 text-white font-bold cursor-pointer">
            Finish Tour
          </Button>
        </div>
      )}
    </>
  );
};
