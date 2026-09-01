import { afterEach, describe, expect, it } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "../context/AuthContext";
import { UploadQueueProvider, useUploadQueue } from "../context/UploadQueueContext";
import { UploadDropzone } from "../components/documents/UploadDropzone";

afterEach(() => {
  localStorage.clear();
});

function Probe() {
  const { addFiles } = useUploadQueue();
  return (
    <div>
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
      <button onClick={() => addFiles([new File(["x"], "ok.pdf", { type: "application/pdf" })])}>
        add-doc
      </button>
    </div>
  );
}

const renderDropzone = () =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: { queries: { retry: false } },
        })
      }
    >
      <AuthProvider>
        <UploadQueueProvider>
          <UploadDropzone />
          <Probe />
        </UploadQueueProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );

describe("UploadDropzone", () => {
  it("never renders chat-composer rows in the documents queue", async () => {
    renderDropzone();

    // A chat row (scoped to a conversation) must not leak into this queue…
    screen.getByText("add-chat").click();
    expect(screen.queryByText("chat.png")).not.toBeInTheDocument();
    expect(screen.queryByText("Upload Queue")).not.toBeInTheDocument();

    // …while a document row shows up as usual.
    screen.getByText("add-doc").click();
    expect(await screen.findByText("ok.pdf")).toBeInTheDocument();
    expect(screen.getByText(/Upload Queue \(1\)/)).toBeInTheDocument();
    expect(screen.queryByText("chat.png")).not.toBeInTheDocument();
    await act(async () => {});
  });

  it("notes chat-composer uploads when the queue would otherwise look empty", async () => {
    renderDropzone();

    expect(screen.queryByText(/in progress from the chat composer/i)).not.toBeInTheDocument();

    screen.getByText("add-chat").click();
    expect(
      await screen.findByText(/1 upload in progress from the chat composer/i),
    ).toBeInTheDocument();
    await act(async () => {});
  });
});
