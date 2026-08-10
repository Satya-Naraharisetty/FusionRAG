import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ChatInput } from "../components/chat/ChatInput";

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

const renderWithQueryClient = (ui: React.ReactElement) => {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
};

describe("ChatInput", () => {
  it("renders textarea correctly", () => {
    renderWithQueryClient(
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
    renderWithQueryClient(
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

    expect(handleSend).toHaveBeenCalledWith("Hello assistant", undefined);
  });

  it("shows the document-mode indicator when @documents is typed", () => {
    renderWithQueryClient(
      <ChatInput
        conversationId={null}
        onSend={() => {}}
        onStop={() => {}}
        isStreaming={false}
      />
    );

    const textarea = screen.getByPlaceholderText(/Message Hybrid RAG/i);
    expect(screen.queryByText(/Document mode/i)).not.toBeInTheDocument();

    fireEvent.change(textarea, {
      target: { value: "@documents What is RAG?" },
    });
    expect(screen.getByText(/Document mode/i)).toBeInTheDocument();

    fireEvent.change(textarea, { target: { value: "What is RAG?" } });
    expect(screen.queryByText(/Document mode/i)).not.toBeInTheDocument();
  });

  it("renders stop button instead of send when streaming", () => {
    const handleStop = vi.fn();
    renderWithQueryClient(
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

