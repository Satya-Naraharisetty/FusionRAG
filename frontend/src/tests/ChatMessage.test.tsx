import { Suspense } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChatMessage } from "../components/chat/ChatMessage";

const renderWithSuspense = (ui: React.ReactElement) =>
  render(<Suspense fallback={null}>{ui}</Suspense>);

describe("ChatMessage", () => {
  it("renders user message correctly", async () => {
    const msg = {
      id: "msg-1",
      role: "user" as const,
      content: "Hello assistant",
      created_at: new Date().toISOString(),
    };
    renderWithSuspense(<ChatMessage message={msg} />);
    // MarkdownRenderer is lazy, so wait for it to resolve.
    expect(await screen.findByText("Hello assistant")).toBeInTheDocument();
  });

  it("renders assistant message correctly", async () => {
    const msg = {
      id: "msg-2",
      role: "assistant" as const,
      content: "Hi user!",
      created_at: new Date().toISOString(),
    };
    renderWithSuspense(<ChatMessage message={msg} />);
    expect(await screen.findByText("Hi user!")).toBeInTheDocument();
  });
});
