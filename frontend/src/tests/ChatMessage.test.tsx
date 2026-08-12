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

  it("shows the general-knowledge hint when retrieval was skipped", async () => {
    const msg = {
      id: "msg-3",
      role: "assistant" as const,
      content: "A general-knowledge answer.",
      status: "completed" as const,
      retrievalSkipped: true,
      created_at: new Date().toISOString(),
    };
    renderWithSuspense(<ChatMessage message={msg} />);
    expect(
      await screen.findByText(
        /Answering from general knowledge — attach files here or use @documents/
      )
    ).toBeInTheDocument();
  });

  it("does not show the hint when retrieval ran normally", async () => {
    const msg = {
      id: "msg-4",
      role: "assistant" as const,
      content: "A grounded answer.",
      status: "completed" as const,
      retrievalSkipped: false,
      created_at: new Date().toISOString(),
    };
    renderWithSuspense(<ChatMessage message={msg} />);
    await screen.findByText("A grounded answer.");
    expect(
      screen.queryByText(/Answering from general knowledge/)
    ).not.toBeInTheDocument();
  });
});
