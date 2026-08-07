import React from "react";
import { Sparkles, MessageSquare, BookOpen, Search } from "lucide-react";

interface EmptyChatProps {
  onSelectPrompt: (prompt: string) => void;
}

export const EmptyChat: React.FC<EmptyChatProps> = ({ onSelectPrompt }) => {
  const examples = [
    {
      icon: <BookOpen size={16} className="text-violet-400" />,
      title: "Summarize a document",
      desc: "Get key takeaways from your uploaded files instantly.",
      prompt: "Can you provide a comprehensive summary of my uploaded documents?",
    },
    {
      icon: <Search size={16} className="text-fuchsia-400" />,
      title: "Hybrid Search retrieval",
      desc: "Query specific details across vector and sparse DBs.",
      prompt: "Find all key references to security policies inside the documents.",
    },
    {
      icon: <Sparkles size={16} className="text-amber-400" />,
      title: "Explain complex concepts",
      desc: "Break down terms using context-grounded sources.",
      prompt: "Explain how our retrieval pipeline merges vector and sparse results.",
    },
    {
      icon: <MessageSquare size={16} className="text-emerald-400" />,
      title: "Compare documents",
      desc: "Analyze differences in two file contents.",
      prompt: "Compare the architecture guidelines in file A and file B.",
    },
  ];

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6 text-center max-w-2xl mx-auto my-auto select-none">
      {/* Decorative center logo with glowing ring */}
      <div className="relative mb-6 group">
        <div className="absolute inset-0 bg-gradient-to-br from-violet-600 to-fuchsia-600 rounded-2xl blur-md opacity-70 group-hover:opacity-100 transition-opacity duration-500 animate-pulse" />
        <div className="relative flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-600 to-fuchsia-600 text-white font-extrabold text-xl shadow-lg transition-transform duration-300 group-hover:scale-105">
          H
        </div>
      </div>

      <h2 className="text-xl font-extrabold font-title tracking-tight bg-gradient-to-r from-zinc-100 via-zinc-200 to-zinc-400 bg-clip-text text-transparent mb-2">
        Hybrid RAG Assistant
      </h2>
      <p className="text-xs text-zinc-400 mb-8 max-w-md leading-relaxed">
        Upload PDF, TXT, DOCX or MD files to index them, then chat with your database using grounded, high-fidelity LLM responses.
      </p>

      {/* Grid of premium glass cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 w-full">
        {examples.map((item, idx) => (
          <div
            key={idx}
            onClick={() => onSelectPrompt(item.prompt)}
            className="flex flex-col items-start text-left p-4.5 bg-zinc-900/10 backdrop-blur-md border border-zinc-900/80 hover:border-violet-500/30 hover:bg-violet-950/5 rounded-xl cursor-pointer transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_8px_30px_rgb(0,0,0,0.3),0_0_15px_rgba(139,92,246,0.1)] group"
          >
            <div className="flex items-center gap-2.5 mb-2">
              <div className="p-1.5 rounded-lg bg-zinc-900/60 border border-zinc-800/40 group-hover:bg-violet-950/20 group-hover:border-violet-500/20 transition-colors duration-300">
                {item.icon}
              </div>
              <h3 className="text-xs font-bold text-zinc-200 group-hover:text-zinc-100 transition-colors duration-300">
                {item.title}
              </h3>
            </div>
            <p className="text-[10px] text-zinc-500 group-hover:text-zinc-400 leading-relaxed transition-colors duration-300">
              {item.desc}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
};
