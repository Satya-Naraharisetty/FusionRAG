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
    <div className="flex-1 flex flex-col items-center justify-center p-6 text-center max-w-2xl mx-auto mt-8">
      {/* Decorative center logo */}
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-600 to-fuchsia-600 text-white font-extrabold text-lg shadow-lg mb-4 animate-bounce duration-[3000ms]">
        H
      </div>
      <h2 className="text-lg font-bold font-title text-zinc-100 mb-1">
        Hybrid RAG Assistant
      </h2>
      <p className="text-xs text-zinc-400 mb-8 max-w-md">
        Upload PDF, TXT, DOCX or MD files to index them, then chat with your database using grounded LLM responses.
      </p>

      {/* Grid of cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full">
        {examples.map((item, idx) => (
          <div
            key={idx}
            onClick={() => onSelectPrompt(item.prompt)}
            className="flex flex-col items-start text-left p-4 bg-zinc-950/40 hover:bg-zinc-900/40 border border-zinc-900 hover:border-zinc-800 rounded-xl cursor-pointer transition-all duration-200 group shadow-sm"
          >
            <div className="flex items-center gap-2.5 mb-1.5">
              {item.icon}
              <h3 className="text-xs font-bold text-zinc-200 group-hover:text-zinc-100">
                {item.title}
              </h3>
            </div>
            <p className="text-[10px] text-zinc-500 group-hover:text-zinc-400 leading-normal">
              {item.desc}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
};
