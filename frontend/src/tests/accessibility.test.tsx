import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ChatInput } from "../components/chat/ChatInput";
import { AuthProvider } from "../context/AuthContext";
import { UploadQueueProvider } from "../context/UploadQueueContext";

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

const renderWithProviders = (ui: React.ReactElement) => {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <UploadQueueProvider>{ui}</UploadQueueProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
};

describe("Frontend Accessibility (a11y) & WCAG Compliance", () => {
  it("ChatInput has accessible textarea role and accessible submit/stop buttons", () => {
    const onSend = vi.fn();
    const onStop = vi.fn();

    renderWithProviders(
      <ChatInput conversationId={null} onSend={onSend} onStop={onStop} isStreaming={false} />,
    );

    // 1. Textarea must have accessible textbox role and placeholder/label
    const textbox = screen.getByRole("textbox");
    expect(textbox).toBeInTheDocument();
    expect(textbox).toHaveAttribute("placeholder");

    // 2. Attach button must have accessible aria-label or title
    const attachButton = screen.getByRole("button", { name: /attach/i });
    expect(attachButton).toBeInTheDocument();
    expect(attachButton).not.toBeDisabled();

    // 3. Send button must have accessible label and be disabled when input is empty
    const sendButton = screen.getByRole("button", { name: /send/i });
    expect(sendButton).toBeInTheDocument();
    expect(sendButton).toBeDisabled();
  });

  it("Stop button has accessible role and label when streaming is active", () => {
    const onSend = vi.fn();
    const onStop = vi.fn();

    renderWithProviders(
      <ChatInput conversationId={null} onSend={onSend} onStop={onStop} isStreaming={true} />,
    );

    // Stop button replaces send button when streaming
    const stopButton = screen.getByRole("button", { name: /stop/i });
    expect(stopButton).toBeInTheDocument();
    expect(stopButton).not.toBeDisabled();

    fireEvent.click(stopButton);
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("Keyboard navigation: textarea allows typing and Enter key submission without mouse", () => {
    const onSend = vi.fn();
    const onStop = vi.fn();

    renderWithProviders(
      <ChatInput conversationId={null} onSend={onSend} onStop={onStop} isStreaming={false} />,
    );

    const textbox = screen.getByRole("textbox");
    fireEvent.change(textbox, { target: { value: "Accessible query message" } });

    // Send button becomes enabled
    const sendButton = screen.getByRole("button", { name: /send/i });
    expect(sendButton).not.toBeDisabled();

    // Pressing Enter key sends message
    fireEvent.keyDown(textbox, { key: "Enter", shiftKey: false });
    expect(onSend).toHaveBeenCalledWith("Accessible query message", undefined);
  });
});
