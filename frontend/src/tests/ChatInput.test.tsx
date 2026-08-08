import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatInput } from "../components/chat/ChatInput";

describe("ChatInput", () => {
  it("renders textarea correctly", () => {
    render(
      <ChatInput
        conversationId={null}
        onSend={() => {}}
        onStop={() => {}}
        isStreaming={false}
      />
    );
    expect(screen.getByPlaceholderText(/Message Hybrid RAG/i)).toBeInTheDocument();
  });

  it("triggers onSend when submitting text", () => {
    const handleSend = vi.fn();
    render(
      <ChatInput
        conversationId={null}
        onSend={handleSend}
        onStop={() => {}}
        isStreaming={false}
      />
    );

    const textarea = screen.getByPlaceholderText(/Message Hybrid RAG/i);
    fireEvent.change(textarea, { target: { value: "Hello assistant" } });
    
    const form = textarea.closest("form");
    if (form) {
      fireEvent.submit(form);
    }

    expect(handleSend).toHaveBeenCalledWith("Hello assistant");
  });

  it("renders stop button instead of send when streaming", () => {
    const handleStop = vi.fn();
    render(
      <ChatInput
        conversationId={null}
        onSend={() => {}}
        onStop={handleStop}
        isStreaming={true}
      />
    );

    const stopBtn = screen.getByRole("button", { name: /Stop generation/i });
    expect(stopBtn).toBeInTheDocument();
    
    fireEvent.click(stopBtn);
    expect(handleStop).toHaveBeenCalled();
  });
});
