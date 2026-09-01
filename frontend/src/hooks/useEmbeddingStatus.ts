import { useMemo } from "react";
import { useQueries, type Query } from "@tanstack/react-query";
import { documentsApi } from "../api/documents";
import { QUERY_KEYS } from "../lib/constants";
import { EMBEDDING_POLL_INTERVAL_MS } from "../lib/uploadStages";
import { type EmbeddingStatus } from "../types";
import { useDocuments } from "./useDocuments";

/**
 * Polls embedding status for documents whose chunking has finished, returning
 * a map of document id → EmbeddingStatus.
 *
 * Built on React Query so every surface that mounts this hook shares one
 * cache: the sidebar summary and the Documents page both call it, and the
 * per-doc queries are deduped by key (`["embedding-status", id, updatedAt]`).
 * The underlying documents query already refetches every 5s while anything is
 * pending/processing, which covers the chunking pipeline; this hook picks up
 * the vector-DB stage (real `embedded_chunks`/`chunks_total` counts) that
 * follows.
 *
 * The document's `updated_at` in the query key restarts the query when a
 * document is reprocessed (the embedding job runs again from scratch), and
 * the functional `refetchInterval` stops polling once a status resolves to
 * `completed`. `failed` keeps polling so a Regenerate action (which
 * invalidates these queries) is picked up — a stale "failed" read right
 * after the job is queued must not kill the poll and strand the card's
 * amber banner until reload.
 */
export function useEmbeddingStatus(
  extraDocumentIds: string[] = [],
): Record<string, EmbeddingStatus> {
  const { data: documents = [] } = useDocuments();

  const extraIds = useMemo(() => [...new Set(extraDocumentIds)], [extraDocumentIds]);

  // Targets = documents from the global library whose chunking finished, plus
  // any explicitly-listed ids — chat-scoped uploads aren't part of the global
  // list, but their embedding job must be polled the same way so the composer
  // tray flips to done/error.
  const targets = useMemo(() => {
    const seen = new Set<string>();
    const list: Array<{ id: string; updatedAt: string }> = [];
    documents.forEach((d) => {
      if (d.status === "completed" && !seen.has(d.id)) {
        seen.add(d.id);
        list.push({ id: d.id, updatedAt: d.updated_at });
      }
    });
    extraIds.forEach((id) => {
      if (!seen.has(id)) {
        seen.add(id);
        // No updated_at known for chat-scoped docs; the poll simply runs
        // until the status resolves to completed.
        list.push({ id, updatedAt: "" });
      }
    });
    return list;
  }, [documents, extraIds]);

  const queries = useQueries({
    queries: targets.map((doc) => ({
      queryKey: [QUERY_KEYS.EMBEDDING_STATUS, doc.id, doc.updatedAt],
      queryFn: () => documentsApi.getEmbeddingStatus(doc.id),
      // `.map()` breaks contextual typing into useQueries' generic options,
      // so the callback parameter needs an explicit Query annotation.
      refetchInterval: (query: Query<EmbeddingStatus>) =>
        query.state.data?.status === "completed" ? false : EMBEDDING_POLL_INTERVAL_MS,
    })),
  });

  return useMemo(() => {
    const map: Record<string, EmbeddingStatus> = {};
    targets.forEach((doc, i) => {
      const data = queries[i]?.data;
      if (data) map[doc.id] = data;
    });
    return map;
  }, [targets, queries]);
}
