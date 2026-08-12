import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DocumentCard } from "../components/documents/DocumentCard";
import { VECTORIZATION_FAILED_MESSAGE } from "../lib/uploadStages";
import { Document } from "../types";

const baseDoc: Document = {
  id: "doc-1",
  user_id: "u",
  conversation_id: null,
  filename: "a.pdf",
  original_filename: "a.pdf",
  content_type: "application/pdf",
  file_size: 100,
  checksum: "x",
  status: "processing",
  extractor_version: "1.0",
  failure_reason: null,
  page_count: null,
  word_count: null,
  language: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  processing_started_at: null,
  processing_completed_at: null,
};

const renderCard = ({
  processingStep = null,
  embeddingFailed = false,
  onRegenerateEmbeddings = async () => {},
}: {
  processingStep?: { progress: number; detail: string } | null;
  embeddingFailed?: boolean;
  onRegenerateEmbeddings?: () => Promise<unknown>;
} = {}) =>
  render(
    <DocumentCard
      document={baseDoc}
      processingStep={processingStep}
      embeddingFailed={embeddingFailed}
      onDelete={async () => {}}
      onReprocess={async () => {}}
      onRegenerateEmbeddings={onRegenerateEmbeddings}
      isSelected={false}
      onSelectToggle={() => {}}
      documentFolders={[]}
      onMoveToFolder={() => {}}
      onDuplicate={() => {}}
      onExport={() => {}}
    />
  );

describe("DocumentCard pipeline step footer", () => {
  it("renders the animated step line and progress while processing", () => {
    renderCard({
      processingStep: {
        progress: 80,
        detail: "Indexing into vector DB — 4 of 10 chunks embedded",
      },
    });

    expect(
      screen.getByText("Indexing into vector DB — 4 of 10 chunks embedded")
    ).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument();
  });

  it("renders nothing extra when the document is idle", () => {
    renderCard({ processingStep: null });

    expect(
      screen.queryByText(/Indexing into vector DB/)
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/%$/)).not.toBeInTheDocument();
  });
});

describe("DocumentCard vectorization failure banner", () => {
  it("renders the amber banner with a regenerate action when vectorization failed", () => {
    renderCard({ embeddingFailed: true });

    expect(screen.getByText(VECTORIZATION_FAILED_MESSAGE)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Regenerate/i })
    ).toBeInTheDocument();
  });

  it("regenerate button triggers onRegenerateEmbeddings for the document", async () => {
    const regenerate = vi.fn(async () => {});
    renderCard({ embeddingFailed: true, onRegenerateEmbeddings: regenerate });

    fireEvent.click(screen.getByRole("button", { name: /Regenerate/i }));
    await waitFor(() => expect(regenerate).toHaveBeenCalledWith("doc-1"));
  });

  it("renders no banner when vectorization is healthy", () => {
    renderCard({ embeddingFailed: false });

    expect(
      screen.queryByText(VECTORIZATION_FAILED_MESSAGE)
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Regenerate/i })
    ).not.toBeInTheDocument();
  });
});
