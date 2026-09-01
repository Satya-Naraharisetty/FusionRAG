import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "../context/AuthContext";
import { UploadQueueProvider, useUploadQueue } from "../context/UploadQueueContext";
import { ConversationDocumentChips } from "../components/chat/ConversationDocumentChips";
import { server } from "./handlers";

afterEach(() => {
  localStorage.clear();
});

const chatDoc = (id: string, name: string) => ({
  id,
  user_id: "user-123",
  conversation_id: "conv-1",
  filename: name,
  original_filename: name,
  content_type: "application/pdf",
  file_size: 10,
  checksum: "x",
  status: "completed" as const,
  extractor_version: "1.0",
  failure_reason: null,
  page_count: null,
  word_count: null,
  language: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
});

// Lets the test add a chat upload through the queue (as the composer does) so
// the remove handler's queue-row cleanup can be asserted.
function QueueProbe() {
  const { queue, addFiles } = useUploadQueue();
  return (
    <div>
      <button
        onClick={() =>
          addFiles([new File(["x"], "a.pdf", { type: "application/pdf" })], {
            source: "chat",
            conversationId: "conv-1",
            acceptedExtensions: ["pdf"],
            autoUpload: true,
            silent: true,
          })
        }
      >
        add-chat
      </button>
      <span data-testid="queue-count">{queue.length}</span>
      <ul>
        {queue.map((q) => (
          <li key={q.id} data-testid="queue-row" data-doc={q.documentId ?? ""}>
            {q.fileName}
          </li>
        ))}
      </ul>
    </div>
  );
}

const renderWithQueue = (ui: React.ReactElement) =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <AuthProvider>
        <UploadQueueProvider>{ui}</UploadQueueProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );

describe("ConversationDocumentChips", () => {
  it("renders the conversation's chat-scoped documents as chips", async () => {
    server.use(
      http.get("*/api/v1/documents", ({ request }) => {
        const conv = new URL(request.url).searchParams.get("conversation_id");
        return HttpResponse.json(
          conv ? [chatDoc("chat-doc-1", "a.pdf"), chatDoc("chat-doc-2", "b.pdf")] : [],
        );
      }),
    );

    renderWithQueue(<ConversationDocumentChips conversationId="conv-1" />);

    expect(await screen.findByText("a.pdf")).toBeInTheDocument();
    expect(screen.getByText("b.pdf")).toBeInTheDocument();
    expect(screen.getByText(/only this conversation can use them/i)).toBeInTheDocument();
    // The caption under the chips spells out the two-tier lifecycle.
    expect(
      screen.getByText(/Only usable in this chat — deleted with the conversation/i),
    ).toBeInTheDocument();
    await act(async () => {});
  });

  it("renders nothing without a conversation", async () => {
    renderWithQueue(<ConversationDocumentChips conversationId={null} />);
    expect(screen.queryByText(/only this conversation can use them/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Only usable in this chat — deleted with the conversation/i),
    ).not.toBeInTheDocument();
    await act(async () => {});
  });

  it("shows the lifecycle caption in the empty state before any files are attached", async () => {
    server.use(http.get("*/api/v1/documents", () => HttpResponse.json([])));

    renderWithQueue(<ConversationDocumentChips conversationId="conv-1" />);

    // No files yet — the strip shows just the lifecycle note, so users know
    // chat files die with the conversation before attaching anything.
    expect(
      await screen.findByText(/Only usable in this chat — deleted with the conversation/i),
    ).toBeInTheDocument();
    // No header and no chips in the empty state.
    expect(screen.queryByText(/only this conversation can use them/i)).not.toBeInTheDocument();
    await act(async () => {});
  });

  it("removing a chip deletes the document and drops its queue row", async () => {
    // Stateful mock: the conversation's docs list starts with both files and
    // DELETE removes one, so the chip actually disappears after refetch.
    let convDocs = [chatDoc("chat-doc-1", "a.pdf"), chatDoc("chat-doc-2", "b.pdf")];
    server.use(
      http.get("*/api/v1/documents", ({ request }) => {
        const conv = new URL(request.url).searchParams.get("conversation_id");
        return HttpResponse.json(conv ? convDocs : []);
      }),
      http.delete("*/api/v1/documents/:id", ({ params }) => {
        convDocs = convDocs.filter((d) => d.id !== params.id);
        return new HttpResponse(null, { status: 204 });
      }),
      // The queue's autoUpload POST resolves to chat-doc-1 (the same doc the
      // conversation list returns), so the chip's remove must also cancel the
      // matching in-flight queue row.
      http.post("*/api/v1/documents/upload", () =>
        HttpResponse.json(chatDoc("chat-doc-1", "a.pdf")),
      ),
    );

    renderWithQueue(
      <div>
        <QueueProbe />
        <ConversationDocumentChips conversationId="conv-1" />
      </div>,
    );

    // Attach a file through the queue — its row gains documentId chat-doc-1
    // once the mocked upload resolves.
    fireEvent.click(screen.getByText("add-chat"));
    await waitFor(() => expect(screen.getByTestId("queue-count")).toHaveTextContent("1"));
    await waitFor(() => {
      const rows = screen.getAllByTestId("queue-row");
      expect(rows[0].getAttribute("data-doc")).toBe("chat-doc-1");
    });

    // Both server-side chat docs render as chips. Queried via the unique
    // remove-button aria-label because the queue row <li> also displays
    // "a.pdf" (the composer tray), so plain text queries would be ambiguous.
    expect(
      await screen.findByRole("button", {
        name: "Remove a.pdf from this chat",
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove b.pdf from this chat" })).toBeInTheDocument();

    // Removing a.pdf deletes it server-side (chip disappears) and drops the
    // queue row for the same document.
    fireEvent.click(screen.getByRole("button", { name: "Remove a.pdf from this chat" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("button", {
          name: "Remove a.pdf from this chat",
        }),
      ).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Remove b.pdf from this chat" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("queue-count")).toHaveTextContent("0"));
    await act(async () => {});
  });
});
