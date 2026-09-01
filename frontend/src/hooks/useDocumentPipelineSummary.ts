import { useMemo } from "react";
import { summarizeDocumentPipeline } from "../lib/uploadStages";
import { useDocuments } from "./useDocuments";
import { useEmbeddingStatus } from "./useEmbeddingStatus";

/**
 * Summarizes the user's document-ingestion pipeline for sidebar surfaces
 * (e.g. the Documents button tooltip). The documents query already refetches
 * every 5s while anything is pending/processing, and useEmbeddingStatus covers
 * the vector-DB stage, so the summary stays live through the whole pipeline
 * and goes idle once everything is indexed.
 */
export function useDocumentPipelineSummary() {
  const { data: documents = [] } = useDocuments();
  const embeddingStatus = useEmbeddingStatus();

  return useMemo(
    () => summarizeDocumentPipeline(documents, embeddingStatus),
    [documents, embeddingStatus],
  );
}
