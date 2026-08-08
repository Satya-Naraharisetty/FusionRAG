import React from "react";

interface EmptyChatProps {
  onSelectPrompt: (prompt: string) => void;
}

export const EmptyChat: React.FC<EmptyChatProps> = ({ onSelectPrompt }) => {
  const examples = [
    {
      label: "Summarize my documents",
      prompt: "Can you provide a comprehensive summary of my uploaded documents?",
      icon: "📄",
    },
    {
      label: "Explain this concept",
      prompt: "Explain how our retrieval pipeline merges vector and sparse results.",
      icon: "💡",
    },
    {
      label: "Search my knowledge base",
      prompt: "Find all key references to security policies inside the documents.",
      icon: "🔍",
    },
    {
      label: "Compare these documents",
      prompt: "Compare the architecture guidelines in file A and file B.",
      icon: "⚖️",
    },
  ];

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 pb-8 select-none animate-in fade-in duration-300">
      <div
        style={{
          width: "100%",
          maxWidth: "600px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          textAlign: "center",
          gap: 0,
        }}
      >
        {/* Logo Badge */}
        <div
          style={{
            width: "48px",
            height: "48px",
            borderRadius: "14px",
            background: "linear-gradient(135deg, hsl(250,84%,63%) 0%, hsl(282,84%,60%) 100%)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: "24px",
            boxShadow: "0 0 24px hsla(250,84%,63%,0.3)",
            flexShrink: 0,
            transition: "transform 0.2s ease",
          }}
          className="hover:scale-105"
        >
          <span
            style={{
              color: "white",
              fontWeight: 800,
              fontSize: "20px",
              fontFamily: "var(--font-title, Outfit, Inter, sans-serif)",
              lineHeight: 1,
            }}
          >
            H
          </span>
        </div>

        {/* Main Heading */}
        <h2
          style={{
            fontSize: "30px",
            fontWeight: 700,
            letterSpacing: "-0.02em",
            color: "var(--text-primary, #F5F5F5)",
            fontFamily: "var(--font-title, Outfit, Inter, sans-serif)",
            lineHeight: 1.2,
            marginBottom: "12px",
          }}
        >
          How can I help you today?
        </h2>

        {/* Supporting text */}
        <p
          style={{
            fontSize: "15px",
            lineHeight: 1.65,
            color: "var(--text-secondary, #A3A3A3)",
            maxWidth: "480px",
            marginBottom: "36px",
          }}
        >
          Upload PDF, TXT, DOCX, or MD files to your library, then ask
          questions to search and retrieve grounded insights.
        </p>

        {/* Prompt Grid */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(2, 1fr)",
            gap: "10px",
            width: "100%",
          }}
        >
          {examples.map((item, idx) => (
            <button
              key={idx}
              onClick={() => onSelectPrompt(item.prompt)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                padding: "14px 16px",
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: "12px",
                cursor: "pointer",
                textAlign: "left",
                transition: "all 0.18s ease",
                minHeight: "52px",
              }}
              className="hover:bg-white/[0.07] hover:border-white/[0.12]"
              aria-label={item.label}
            >
              <span style={{ fontSize: "16px", flexShrink: 0, lineHeight: 1 }}>
                {item.icon}
              </span>
              <span
                style={{
                  fontSize: "14px",
                  fontWeight: 500,
                  color: "var(--text-primary, #F5F5F5)",
                  lineHeight: 1.35,
                }}
              >
                {item.label}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
