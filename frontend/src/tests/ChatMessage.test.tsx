import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChatMessage } from "../components/chat/ChatMessage";

describe("ChatMessage", () => {
  it("renders user message correctly", () => {
    const msg = {
      id: "msg-1",
      role: "user" as const,
      content: "Hello assistant",
      created_at: new Date().toISOString(),
    };
    render(<ChatMessage message={msg} />);
    expect(screen.getByText("Hello assistant")).toBeInTheDocument();
  });

  it("renders assistant message correctly", () => {
    const msg = {
      id: "msg-2",
      role: "assistant" as const,
      content: "Hi user!",
      created_at: new Date().toISOString(),
    };
    render(<ChatMessage message={msg} />);
    expect(screen.getByText("Hi user!")).toBeInTheDocument();
  });
});
