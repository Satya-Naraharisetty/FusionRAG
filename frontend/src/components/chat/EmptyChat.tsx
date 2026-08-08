import React from "react";

interface EmptyChatProps {
  onSelectPrompt: (prompt: string) => void;
}

export const EmptyChat: React.FC<EmptyChatProps> = ({ onSelectPrompt }) => {
  const examples = [
    {
      label: "Summarize my documents",
      prompt: "Can you provide a comprehensive summary of my uploaded documents?",
    },
    {
      label: "Explain this concept",
      prompt: "Explain how our retrieval pipeline merges vector and sparse results.",
    },
    {
      label: "Search my knowledge base",
      prompt: "Find all key references to security policies inside the documents.",
    },
    {
      label: "Compare these documents",
      prompt: "Compare the architecture guidelines in file A and file B.",
    },
  ];

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6 pb-24 text-center max-w-2xl mx-auto my-auto select-none animate-in fade-in duration-300">
      {/* Premium Minimal Logo */}
      <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-zinc-900 dark:bg-zinc-100 text-white dark:text-black font-extrabold text-lg shadow-xs mb-5 transition-transform duration-300 hover:scale-105 select-none">
        H
      </div>

      <h2 className="text-xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100 mb-2">
        How can I help you today?
      </h2>
      <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-8 max-w-md leading-relaxed">
        Upload PDF, TXT, DOCX, or MD files to your library, then ask questions to search and retrieve insights from your grounded knowledge base.
      </p>

      {/* Grid of subtle prompts */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-lg">
        {examples.map((item, idx) => (
          <button
            key={idx}
            onClick={() => onSelectPrompt(item.prompt)}
            className="flex items-center justify-start px-4 py-3 bg-zinc-50 dark:bg-zinc-900/10 hover:bg-zinc-100 dark:hover:bg-zinc-900/40 border border-zinc-200/50 dark:border-[var(--border-color)] hover:border-zinc-300 dark:hover:border-[var(--border-hover)] text-zinc-700 dark:text-zinc-300 text-xs rounded-xl cursor-pointer transition-all duration-200 text-left font-medium"
          >
            <span>{item.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
};
