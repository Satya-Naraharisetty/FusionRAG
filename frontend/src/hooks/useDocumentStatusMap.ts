import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { documentsApi } from "../api/documents";
import { QUERY_KEYS } from "../lib/constants";
import { Document } from "../types";

/**
 * Live status for a set of document ids that are NOT part of the global
 * documents list — i.e. chat-scoped documents currently ingesting in the
 * upload queue. `getDocument` is owner-scoped and returns any of the user's
 * documents regardless of scope, so it can resolve chat docs the Documents
 * library deliberately excludes.
 *
 * Returns a Map of document id → Document, or null when the document is gone
 * (deleted/never registered), letting the queue's reconciliation flag such a
 * row as orphaned instead of spinning forever.
 */
export function useDocumentStatusMap(
  documentIds: string[],
): Map<string, Document | null> | undefined {
  const ids = useMemo(() => [...new Set(documentIds)].sort(), [documentIds]);
  const idKey = ids.join("|");

  const query = useQuery({
    queryKey: [QUERY_KEYS.DOCUMENTS, "status-map", idKey],
    queryFn: async () => {
      const results = await Promise.allSettled(ids.map((id) => documentsApi.getDocument(id)));
      return new Map<string, Document | null>(
        ids.map((id, i) => {
          const r = results[i];
          return [id, r.status === "fulfilled" ? r.value : null];
        }),
      );
    },
    enabled: ids.length > 0,
    refetchInterval: 5000,
    staleTime: 2000,
    // Map instances are returned as-is; TanStack's structural sharing does not
    // understand Maps and would otherwise mis-handle refetches.
    structuralSharing: false,
  });

  return query.data;
}
