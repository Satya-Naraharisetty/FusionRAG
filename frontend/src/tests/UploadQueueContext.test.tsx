import { describe, expect, it, afterEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { AuthProvider } from "../context/AuthContext";
import {
  UploadQueueProvider,
  pickSnapshotItems,
  restoreableFromSnapshot,
  useUploadQueue,
  type QueueFile,
} from "../context/UploadQueueContext";
import { server } from "./handlers";

const STORAGE_KEY = "upload-queue-v1";

afterEach(() => {
  localStorage.clear();
});

/* ── Pure snapshot helpers ── */

describe("upload queue snapshot helpers", () => {
  it("pickSnapshotItems drops non-serializable fields and rows the server doesn't know about", () => {
    const queue: QueueFile[] = [
      {
        id: "q1",
        fileName: "a.pdf",
        file: new File(["x"], "a.pdf", { type: "application/pdf" }),
        status: "queued",
        progress: 0,
        source: "documents",
      },
      {
        id: "q2",
        fileName: "b.pdf",
        file: new File(["x"], "b.pdf", { type: "application/pdf" }),
        status: "processing",
        progress: 15,
        documentId: "doc-2",
        startedAt: 123,
        source: "documents",
      },
      {
        id: "q3",
        fileName: "c.pdf",
        file: new File(["x"], "c.pdf", { type: "application/pdf" }),
        status: "completed",
        progress: 100,
        documentId: "doc-3",
        source: "documents",
      },
    ];
    // Completed rows are never resurrected — the snapshot only needs rows
    // that could still be in flight or failed.
    expect(pickSnapshotItems(queue)).toEqual([
      {
        id: "q2",
        fileName: "b.pdf",
        status: "processing",
        progress: 15,
        documentId: "doc-2",
        startedAt: 123,
        source: "documents",
      },
    ]);
  });

  it("restoreableFromSnapshot brings back only in-flight/failed rows for the matching user", () => {
    const snapshot = {
      v: 1 as const,
      userId: "user-123",
      items: [
        {
          id: "q2",
          fileName: "b.pdf",
          status: "processing" as const,
          progress: 15,
          documentId: "doc-2",
          startedAt: 123,
        },
        {
          id: "q3",
          fileName: "c.pdf",
          status: "completed" as const,
          progress: 100,
          documentId: "doc-3",
        },
        {
          id: "q4",
          fileName: "d.pdf",
          status: "error" as const,
          progress: 100,
          documentId: "doc-4",
          detail: "Vectorization failed",
        },
        { id: "q5", fileName: "e.pdf", status: "queued" as const, progress: 0 },
      ],
    };
    const restored = restoreableFromSnapshot(snapshot, "user-123");
    expect(restored.map((i) => i.id)).toEqual(["q2", "q4"]);
    expect(restoreableFromSnapshot(snapshot, "someone-else")).toEqual([]);
    expect(restoreableFromSnapshot(null, "user-123")).toEqual([]);
  });
});

/* ── Provider integration ── */

function Probe() {
  const {
    queue,
    addFiles,
    clearCompleted,
    removeItems,
    discardConversationRows,
    uploadQueuedChatRows,
    discardQueuedNewChatRows,
  } = useUploadQueue();
  const chatPdf = (name: string) => new File(["x"], name, { type: "application/pdf" });
  return (
    <div>
      <button onClick={() => addFiles([new File(["x"], "ok.pdf", { type: "application/pdf" })])}>
        add
      </button>
      <button
        onClick={() =>
          addFiles([new File(["x"], "chat.png", { type: "image/png" })], {
            source: "chat",
            conversationId: "conv-1",
            maxSize: 10 * 1024 * 1024,
            acceptedExtensions: ["png"],
            autoUpload: true,
            silent: true,
          })
        }
      >
        add-chat
      </button>
      <button
        onClick={() =>
          addFiles([new File(["x"], "doc.pdf", { type: "application/pdf" })], {
            autoUpload: true,
            silent: true,
          })
        }
      >
        add-doc-auto
      </button>
      <button
        onClick={() =>
          addFiles([chatPdf("c1.pdf")], {
            source: "chat",
            conversationId: "conv-1",
            acceptedExtensions: ["pdf"],
            autoUpload: false,
            silent: true,
          })
        }
      >
        add-chat-queued-conv1
      </button>
      <button
        onClick={() =>
          addFiles([chatPdf("c2.pdf")], {
            source: "chat",
            conversationId: "conv-2",
            acceptedExtensions: ["pdf"],
            autoUpload: false,
            silent: true,
          })
        }
      >
        add-chat-queued-conv2
      </button>
      <button
        onClick={() =>
          addFiles([chatPdf("new.pdf")], {
            source: "chat",
            acceptedExtensions: ["pdf"],
            autoUpload: false,
            silent: true,
          })
        }
      >
        add-chat-queued-none
      </button>
      <button onClick={() => discardConversationRows("conv-1")}>discard-conv1</button>
      <button onClick={() => uploadQueuedChatRows("conv-9")}>flush-conv9</button>
      <button onClick={discardQueuedNewChatRows}>discard-queued-none</button>
      <button onClick={() => removeItems(queue.map((q) => q.id))}>remove-all</button>
      <button onClick={clearCompleted}>clear-done</button>
      <ul>
        {queue.map((q) => (
          <li
            key={q.id}
            data-status={q.status}
            data-source={q.source}
            data-conv={q.conversationId ?? ""}
          >
            {q.fileName}
          </li>
        ))}
      </ul>
    </div>
  );
}

const renderQueue = (props?: { completedRowTtlMs?: number }) =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: { queries: { retry: false } },
        })
      }
    >
      <AuthProvider>
        <UploadQueueProvider {...props}>
          <Probe />
        </UploadQueueProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );

describe("UploadQueueProvider", () => {
  it("restores the user's in-flight rows and flips them to done once embeddings resolve", async () => {
    server.use(
      http.get("*/api/v1/documents/:id/embeddings/status", () =>
        HttpResponse.json({
          status: "completed",
          chunks_total: 5,
          embedded_chunks: 5,
          failed_chunks: 0,
          provider: "mock",
          model: "mock",
        }),
      ),
    );
    // The mocked auth user is user-123 and the mocked documents list has a
    // completed doc-1, so a restored processing row for doc-1 should reconcile
    // to completed through the shared embedding poll.
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        v: 1,
        userId: "user-123",
        items: [
          {
            id: "q1",
            fileName: "b.pdf",
            status: "processing",
            progress: 15,
            documentId: "doc-1",
            startedAt: Date.now(),
          },
        ],
      }),
    );

    renderQueue();

    await waitFor(() => expect(screen.getByText("b.pdf")).toBeInTheDocument());
    await waitFor(
      () => expect(screen.getByText("b.pdf").getAttribute("data-status")).toBe("completed"),
      { timeout: 5000 },
    );

    // Completed rows can be dismissed with the clear action.
    screen.getByText("clear-done").click();
    await waitFor(() => expect(screen.queryByText("b.pdf")).not.toBeInTheDocument());
    // Settle the auth/documents/embedding queries before the test ends.
    await act(async () => {});
  });

  it("ignores a snapshot belonging to a different user", async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        v: 1,
        userId: "someone-else",
        items: [
          {
            id: "q1",
            fileName: "stale.pdf",
            status: "processing",
            progress: 15,
            documentId: "doc-1",
            startedAt: Date.now(),
          },
        ],
      }),
    );

    renderQueue();

    await waitFor(() => expect(screen.queryByText("stale.pdf")).not.toBeInTheDocument());
    // A foreign user's snapshot is dropped, not kept.
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    await act(async () => {});
  });

  it("addFiles appends a validated queued row", async () => {
    renderQueue();
    screen.getByText("add").click();
    await waitFor(() =>
      expect(screen.getByText("ok.pdf").getAttribute("data-status")).toBe("queued"),
    );
    await act(async () => {});
  });

  it("adds chat rows with conversation scoping and auto-upload", async () => {
    renderQueue();
    screen.getByText("add-chat").click();
    const row = await screen.findByText("chat.png");
    expect(row.getAttribute("data-source")).toBe("chat");
    expect(row.getAttribute("data-conv")).toBe("conv-1");
    // autoUpload starts the upload immediately (mock resolves to processing).
    await waitFor(() => expect(row.getAttribute("data-status")).not.toBe("queued"));
    await act(async () => {});
  });

  it("restores chat rows for their conversation", async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        v: 1,
        userId: "user-123",
        items: [
          {
            id: "q1",
            fileName: "chat.png",
            status: "processing",
            progress: 15,
            documentId: "doc-1",
            startedAt: Date.now(),
            source: "chat",
            conversationId: "conv-1",
          },
        ],
      }),
    );

    renderQueue();

    const row = await screen.findByText("chat.png");
    expect(row.getAttribute("data-source")).toBe("chat");
    expect(row.getAttribute("data-conv")).toBe("conv-1");
    await act(async () => {});
  });

  it("clearCompleted only dismisses document rows, leaving chat rows", async () => {
    renderQueue();
    // Both rows complete through the mock pipeline; the chat row must not be
    // touched by the Documents queue's "Clear done".
    screen.getByText("add-chat").click();
    screen.getByText("add-doc-auto").click();

    await waitFor(() =>
      expect(screen.getByText("chat.png").getAttribute("data-status")).toBe("completed"),
    );
    await waitFor(() =>
      expect(screen.getByText("doc.pdf").getAttribute("data-status")).toBe("completed"),
    );

    fireEvent.click(screen.getByText("clear-done"));
    await waitFor(() => expect(screen.queryByText("doc.pdf")).not.toBeInTheDocument());
    expect(screen.getByText("chat.png")).toBeInTheDocument();
    await act(async () => {});
  });

  it("removeItems drops rows without aborting", async () => {
    renderQueue();
    screen.getByText("add").click();
    await waitFor(() => expect(screen.getByText("ok.pdf")).toBeInTheDocument());
    screen.getByText("remove-all").click();
    await waitFor(() => expect(screen.queryByText("ok.pdf")).not.toBeInTheDocument());
    await act(async () => {});
  });

  it("auto-dismisses completed document rows after the TTL, keeping chat rows", async () => {
    renderQueue({ completedRowTtlMs: 50 });

    screen.getByText("add-chat").click();
    screen.getByText("add-doc-auto").click();
    await waitFor(() =>
      expect(screen.getByText("doc.pdf").getAttribute("data-status")).toBe("completed"),
    );
    await waitFor(() =>
      expect(screen.getByText("chat.png").getAttribute("data-status")).toBe("completed"),
    );

    // The completed document row is dropped moments later (automated "Clear
    // done")…
    await waitFor(() => expect(screen.queryByText("doc.pdf")).not.toBeInTheDocument(), {
      timeout: 2000,
    });
    // …while the chat row keeps its composer lifecycle until sent/cancelled.
    expect(screen.getByText("chat.png")).toBeInTheDocument();
    await act(async () => {});
  });

  it("uploads chat rows scoped to their conversation", async () => {
    // Capture the upload URL so the conversation_id query param is asserted.
    let capturedUrl = "";
    server.use(
      http.post("*/api/v1/documents/upload", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json({
          id: "doc-1",
          user_id: "user-123",
          conversation_id: "conv-1",
          filename: "chat.png",
          original_filename: "chat.png",
          content_type: "image/png",
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

    renderQueue();
    screen.getByText("add-chat").click();
    const row = await screen.findByText("chat.png");
    await waitFor(() => expect(capturedUrl).toContain("conversation_id=conv-1"));
    // The upload actually started (left the queued state).
    await waitFor(() => expect(row.getAttribute("data-status")).not.toBe("queued"));
    await act(async () => {});
  });

  it("restores chat rows and flips them to done through the extra-id embedding poll", async () => {
    // A chat-scoped document is NOT in the global documents list — its row
    // must reconcile through the extra embedding-status ids, not the library.
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        v: 1,
        userId: "user-123",
        items: [
          {
            id: "q1",
            fileName: "chat.png",
            status: "processing",
            progress: 15,
            documentId: "chat-doc-1",
            startedAt: Date.now(),
            source: "chat",
            conversationId: "conv-1",
          },
        ],
      }),
    );

    renderQueue();

    const row = await screen.findByText("chat.png");
    expect(row.getAttribute("data-source")).toBe("chat");
    await waitFor(() => expect(row.getAttribute("data-status")).toBe("completed"), {
      timeout: 5000,
    });
    await act(async () => {});
  });

  it("discardConversationRows removes only that conversation's chat rows", async () => {
    renderQueue();
    screen.getByText("add-chat-queued-conv1").click();
    screen.getByText("add-chat-queued-conv2").click();

    expect(await screen.findByText("c1.pdf")).toBeInTheDocument();
    expect(await screen.findByText("c2.pdf")).toBeInTheDocument();

    // Deleting conv-1 drops its chat rows (and any in-flight uploads) while
    // conv-2's attachments stay queued.
    screen.getByText("discard-conv1").click();
    await waitFor(() => expect(screen.queryByText("c1.pdf")).not.toBeInTheDocument());
    expect(screen.getByText("c2.pdf")).toBeInTheDocument();
    await act(async () => {});
  });

  it("hands deferred new-chat attachments to the created conversation", async () => {
    let capturedUrl = "";
    server.use(
      http.post("*/api/v1/documents/upload", ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json({
          id: "doc-1",
          user_id: "user-123",
          conversation_id: "conv-9",
          filename: "new.pdf",
          original_filename: "new.pdf",
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

    renderQueue();
    // Attached in a brand-new chat (no conversation id yet) — the row stays
    // queued instead of uploading as a global document.
    screen.getByText("add-chat-queued-none").click();
    const row = await screen.findByText("new.pdf");
    expect(row.getAttribute("data-status")).toBe("queued");

    // The conversation is created server-side; the queue hands the deferred
    // rows to it (scoped upload starts) and dismisses them from the tray.
    screen.getByText("flush-conv9").click();
    await waitFor(() => expect(screen.queryByText("new.pdf")).not.toBeInTheDocument());
    await waitFor(() => expect(capturedUrl).toContain("conversation_id=conv-9"));
    await act(async () => {});
  });

  it("discardQueuedNewChatRows drops deferred rows that never found a conversation", async () => {
    renderQueue();
    screen.getByText("add-chat-queued-none").click();
    const row = await screen.findByText("new.pdf");
    expect(row.getAttribute("data-status")).toBe("queued");

    // The user left the brand-new chat without sending — the abandoned draft's
    // rows are cleared so they can't leak into a different conversation.
    screen.getByText("discard-queued-none").click();
    await waitFor(() => expect(screen.queryByText("new.pdf")).not.toBeInTheDocument());
    await act(async () => {});
  });
});
