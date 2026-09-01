import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ChatInput } from "../components/chat/ChatInput";
import { AuthProvider } from "../context/AuthContext";
import { UploadQueueProvider } from "../context/UploadQueueContext";
import { server } from "./handlers";

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

// ChatInput's uploads live in the app-level UploadQueueContext, so the
// provider (with auth) wraps every render — including rerenders, which
// otherwise replace the root element with a provider-less ChatInput.
const renderWithQueryClient = (ui: React.ReactElement) => {
  const queryClient = createTestQueryClient();
  const wrap = (el: React.ReactElement) => (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <UploadQueueProvider>{el}</UploadQueueProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
  const result = render(wrap(ui));
  return { ...result, rerender: (el: React.ReactElement) => result.rerender(wrap(el)) };
};

// The queue persists a per-user snapshot to localStorage — keep tests isolated.
afterEach(() => {
  localStorage.clear();
});

describe("ChatInput", () => {
  it("renders textarea correctly", () => {
    renderWithQueryClient(
      <ChatInput conversationId={null} onSend={() => {}} onStop={() => {}} isStreaming={false} />,
    );
    expect(screen.getByPlaceholderText(/Message FusionRAG/i)).toBeInTheDocument();
    // Brand-new chat, nothing attached yet — the lifecycle note is visible so
    // users know chat files stay in this chat and die with it.
    expect(screen.getByText(/Only usable in this chat/)).toBeInTheDocument();
  });

  it("triggers onSend when submitting text", () => {
    const handleSend = vi.fn();
    renderWithQueryClient(
      <ChatInput conversationId={null} onSend={handleSend} onStop={() => {}} isStreaming={false} />,
    );

    const textarea = screen.getByPlaceholderText(/Message FusionRAG/i);
    fireEvent.change(textarea, { target: { value: "Hello assistant" } });

    const form = textarea.closest("form");
    if (form) {
      fireEvent.submit(form);
    }

    expect(handleSend).toHaveBeenCalledWith("Hello assistant", undefined);
  });

  it("shows the document-mode indicator when @documents is typed", () => {
    renderWithQueryClient(
      <ChatInput conversationId={null} onSend={() => {}} onStop={() => {}} isStreaming={false} />,
    );

    const textarea = screen.getByPlaceholderText(/Message FusionRAG/i);
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
      <ChatInput conversationId={null} onSend={() => {}} onStop={handleStop} isStreaming={true} />,
    );

    const stopBtn = screen.getByRole("button", { name: /Stop generation/i });
    expect(stopBtn).toBeInTheDocument();

    fireEvent.click(stopBtn);
    expect(handleStop).toHaveBeenCalled();
  });

  // Uploads resolve through the mocked POST /documents/upload handler (returns
  // the completed doc-1), after which the row enters "processing" and derives
  // the live pipeline step from the shared documents + embedding-status caches.
  const uploadFile = () => {
    const input = document.getElementById("chat-file-input") as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(["test"], "test.pdf", { type: "application/pdf" })] },
    });
  };

  it("shows the live pipeline step footer while the document ingests", async () => {
    // The document is mid-vectorization: 3 of 5 chunks embedded.
    server.use(
      http.get("*/api/v1/documents/:id/embeddings/status", () =>
        HttpResponse.json({
          status: "generating",
          chunks_total: 5,
          embedded_chunks: 3,
          failed_chunks: 0,
          provider: "mock",
          model: "mock",
        }),
      ),
    );

    renderWithQueryClient(
      <ChatInput conversationId="conv-1" onSend={() => {}} onStop={() => {}} isStreaming={false} />,
    );

    uploadFile();

    // The upload resolves, the row enters processing, and the shared
    // embedding-status poll resolves to "generating" → real step footer.
    expect(
      await screen.findByText("Indexing into vector DB — 3 of 5 chunks embedded"),
    ).toBeInTheDocument();
    expect(screen.getByText("test.pdf")).toBeInTheDocument();
    // The in-flight row carries the same lifecycle hint as the chips strip.
    expect(
      screen.getByText(/Only usable in this chat — deleted with the conversation/),
    ).toBeInTheDocument();
  });

  it("marks the attachment done once the document is fully indexed", async () => {
    // Default handler: embedding status resolves to completed immediately.
    renderWithQueryClient(
      <ChatInput conversationId="conv-1" onSend={() => {}} onStop={() => {}} isStreaming={false} />,
    );

    uploadFile();
    expect(await screen.findByText("test.pdf")).toBeInTheDocument();

    // The completed ring (checkmark) replaces the spinner once embeddings
    // resolve. Scoped to the attachment row (the remove button is a direct
    // child of the row container) so a stray svg elsewhere can't false-pass.
    const row = screen
      .getByRole("button", { name: "Remove test.pdf from this chat" })
      .closest("div");
    expect(row).not.toBeNull();
    await waitFor(() =>
      expect(row!.querySelector("svg polyline[points='20 6 9 17 4 12']")).not.toBeNull(),
    );
    // The pipeline step footer is cleared, not left behind.
    expect(
      screen.queryByText(/Indexing into vector DB|Preparing to index|Extracting text|Chunking/),
    ).toBeNull();
  });

  // Keep the attachment mid-ingest so it can be snapshotted + restored.
  const stayGenerating = () =>
    server.use(
      http.get("*/api/v1/documents/:id/embeddings/status", () =>
        HttpResponse.json({
          status: "generating",
          chunks_total: 5,
          embedded_chunks: 3,
          failed_chunks: 0,
          provider: "mock",
          model: "mock",
        }),
      ),
    );

  it("keeps chat attachments when the composer unmounts and remounts", async () => {
    stayGenerating();

    const { unmount } = renderWithQueryClient(
      <ChatInput conversationId="conv-1" onSend={() => {}} onStop={() => {}} isStreaming={false} />,
    );
    uploadFile();
    expect(await screen.findByText("test.pdf")).toBeInTheDocument();

    // Navigating away unmounts the composer (and its provider); the queue
    // snapshot restores the in-flight row on the way back.
    unmount();
    renderWithQueryClient(
      <ChatInput conversationId="conv-1" onSend={() => {}} onStop={() => {}} isStreaming={false} />,
    );
    expect(await screen.findByText("test.pdf")).toBeInTheDocument();
    await act(async () => {});
  });

  it("scopes chat attachments to the conversation they were attached in", async () => {
    stayGenerating();

    const { rerender } = renderWithQueryClient(
      <ChatInput conversationId="conv-1" onSend={() => {}} onStop={() => {}} isStreaming={false} />,
    );
    uploadFile();
    expect(await screen.findByText("test.pdf")).toBeInTheDocument();

    // A different conversation doesn't see conv-1's attachments…
    rerender(
      <ChatInput conversationId="conv-2" onSend={() => {}} onStop={() => {}} isStreaming={false} />,
    );
    expect(screen.queryByText("test.pdf")).not.toBeInTheDocument();

    // …but they're still there when the user comes back.
    rerender(
      <ChatInput conversationId="conv-1" onSend={() => {}} onStop={() => {}} isStreaming={false} />,
    );
    expect(await screen.findByText("test.pdf")).toBeInTheDocument();
    await act(async () => {});
  });

  it("clears the tray once the message is sent", async () => {
    stayGenerating();
    const handleSend = vi.fn();

    renderWithQueryClient(
      <ChatInput
        conversationId="conv-1"
        onSend={handleSend}
        onStop={() => {}}
        isStreaming={false}
      />,
    );
    uploadFile();
    expect(await screen.findByText("test.pdf")).toBeInTheDocument();

    const textarea = screen.getByPlaceholderText(/Message FusionRAG/i);
    fireEvent.change(textarea, { target: { value: "See attached" } });
    const form = textarea.closest("form");
    if (form) fireEvent.submit(form);

    await waitFor(() => expect(screen.queryByText("test.pdf")).not.toBeInTheDocument());
    // Existing conversation: once the tray clears, no caption lingers here
    // (the chips strip owns the hint for existing chats).
    expect(screen.queryByText(/Only usable in this chat/)).not.toBeInTheDocument();
    await act(async () => {});
  });

  it("defers chat attachments in a brand-new chat until the conversation exists", async () => {
    let uploadCalled = false;
    server.use(
      http.post("*/api/v1/documents/upload", () => {
        uploadCalled = true;
        return HttpResponse.json({
          id: "doc-1",
          user_id: "user-123",
          conversation_id: null,
          filename: "test.pdf",
          original_filename: "test.pdf",
          content_type: "application/pdf",
          file_size: 1,
          checksum: "x",
          status: "completed",
          extractor_version: "1.0",
          failure_reason: null,
          page_count: null,
          word_count: null,
          language: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      }),
    );
    const handleSend = vi.fn();

    renderWithQueryClient(
      <ChatInput conversationId={null} onSend={handleSend} onStop={() => {}} isStreaming={false} />,
    );
    uploadFile();
    expect(await screen.findByText("test.pdf")).toBeInTheDocument();

    // No conversation yet → the row stays queued instead of uploading (a
    // conversation-less upload would leak the file into the global library).
    await act(async () => await new Promise((r) => setTimeout(r, 50)));
    expect(uploadCalled).toBe(false);

    // Sending keeps the deferred rows in the tray — they're handed to the
    // conversation by ChatWindow once the backend creates it.
    const textarea = screen.getByPlaceholderText(/Message FusionRAG/i);
    fireEvent.change(textarea, { target: { value: "with attachment" } });
    const form = textarea.closest("form");
    if (form) fireEvent.submit(form);

    expect(handleSend).toHaveBeenCalledWith("with attachment", [expect.any(File)]);
    expect(screen.getByText("test.pdf")).toBeInTheDocument();
    await act(async () => {});
  });
});
