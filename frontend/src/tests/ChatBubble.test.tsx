import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChatBubble } from "../components/chat/ChatBubble";

describe("ChatBubble", () => {
  it("renders user message correctly", () => {
    const msg = {
      role: "user" as const,
      content: "Hello assistant",
    };
    render(<ChatBubble message={msg} />);
    expect(screen.getByText("Hello assistant")).toBeInTheDocument();
  });

  it("renders assistant message correctly", () => {
    const msg = {
      role: "assistant" as const,
      content: "Hi user!",
    };
    render(<ChatBubble message={msg} />);
    expect(screen.getByText("Hi user!")).toBeInTheDocument();
  });

  it("renders tool call logs when available", () => {
    const msg = {
      role: "assistant" as const,
      content: "Result here",
      toolCalls: [
        {
          id: "tc-1",
          name: "search_db",
          arguments: { query: "test" },
          status: "done" as const,
        },
      ],
    };
    render(<ChatBubble message={msg} />);
    expect(screen.getByText("Tool: search_db")).toBeInTheDocument();
  });
});
