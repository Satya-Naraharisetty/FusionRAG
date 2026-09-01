import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { documentsApi } from "../api/documents";
import { QUERY_KEYS } from "../lib/constants";
import { Document } from "../types";
import toast from "react-hot-toast";
import { useAuth } from "./useAuth";

export const useDocuments = () => {
  const { isAuthenticated } = useAuth();
  return useQuery<Document[]>({
    queryKey: [QUERY_KEYS.DOCUMENTS],
    queryFn: () => documentsApi.listDocuments(),
    enabled: isAuthenticated,
    refetchInterval: (query) => {
      const docs = query.state.data;
      if (!Array.isArray(docs)) return false;
      const hasPendingOrProcessing = docs.some(
        (d) => d.status === "pending" || d.status === "processing",
      );
      return hasPendingOrProcessing ? 5000 : false;
    },
  });
};

/**
 * Documents scoped to a single conversation (chat attachments). The global
 * documents list deliberately excludes these, so they have their own query,
 * keyed by conversation. Refetches every 5s while any doc is still ingesting
 * so newly-attached uploads and their pipeline states appear in the chat.
 */
export const useConversationDocuments = (conversationId: string | null) => {
  const { isAuthenticated } = useAuth();
  return useQuery<Document[]>({
    queryKey: [QUERY_KEYS.DOCUMENTS, "conversation", conversationId],
    queryFn: () => documentsApi.listDocuments(conversationId),
    enabled: Boolean(conversationId) && isAuthenticated,
    refetchInterval: (query) => {
      const docs = query.state.data;
      if (!Array.isArray(docs)) return false;
      const busy = docs.some((d) => d.status === "pending" || d.status === "processing");
      return busy ? 5000 : false;
    },
  });
};

export const useUploadDocument = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      file,
      onProgress,
      signal,
      conversationId,
    }: {
      file: File;
      onProgress?: (progressEvent: unknown) => void;
      signal?: AbortSignal;
      /** Chat-composer uploads are scoped to a conversation (two-tier model). */
      conversationId?: string | null;
    }) => documentsApi.uploadDocument(file, onProgress, signal, conversationId),
    onMutate: async ({ file, conversationId }) => {
      await queryClient.cancelQueries({ queryKey: [QUERY_KEYS.DOCUMENTS] });

      const previousDocs = queryClient.getQueryData<Document[]>([QUERY_KEYS.DOCUMENTS]) || [];

      // Chat-composer uploads belong to their conversation, never to the
      // Documents library — no optimistic row there (the composer tray is the
      // feedback) and the Documents list must not flicker a chat doc.
      if (conversationId) return { previousDocs, tempId: null };

      // Create a temporary optimistic document
      const tempId = Math.random().toString();
      const newDoc: Document = {
        id: tempId,
        user_id: "",
        conversation_id: null,
        filename: file.name,
        original_filename: file.name,
        content_type: file.type || "application/octet-stream",
        file_size: file.size,
        checksum: "",
        status: "pending",
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

      queryClient.setQueryData<Document[]>([QUERY_KEYS.DOCUMENTS], [newDoc, ...previousDocs]);

      return { previousDocs, tempId };
    },
    onError: (err, _variables, context) => {
      if (context?.previousDocs) {
        queryClient.setQueryData([QUERY_KEYS.DOCUMENTS], context.previousDocs);
      }
      // If it wasn't cancelled by the user, show toast
      const isCancelled = err instanceof DOMException && err.name === "AbortError";
      if (!isCancelled) {
        toast.error(`Failed to upload file: ${err.message || err}`);
      }
    },
    onSuccess: (data, variables, context) => {
      if (variables?.conversationId) {
        queryClient.invalidateQueries({
          queryKey: [QUERY_KEYS.DOCUMENTS, "conversation", variables.conversationId],
        });
      }
      if (!context?.tempId) {
        // Chat-scoped upload: nothing optimistic to replace; the composer tray
        // is the feedback, so keep it quiet (matching the pre-queue behaviour)
        // and let the invalidation below reconcile the library list.
        queryClient.invalidateQueries({ queryKey: [QUERY_KEYS.DOCUMENTS] });
        return;
      }
      // Replace optimistic temp file with actual uploaded document
      queryClient.setQueryData<Document[]>([QUERY_KEYS.DOCUMENTS], (old) => {
        if (!old) return [data];
        return old.map((d) => (d.id === context?.tempId ? data : d));
      });
      toast.success(`File "${data.original_filename}" uploaded successfully.`);
    },
    onSettled: (_data, _err, variables) => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEYS.DOCUMENTS] });
      if (variables?.conversationId) {
        queryClient.invalidateQueries({
          queryKey: [QUERY_KEYS.DOCUMENTS, "conversation", variables.conversationId],
        });
      }
    },
  });
};

export const useDeleteDocument = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => documentsApi.deleteDocument(id),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: [QUERY_KEYS.DOCUMENTS] });

      const previousDocs = queryClient.getQueryData<Document[]>([QUERY_KEYS.DOCUMENTS]);

      queryClient.setQueryData<Document[]>([QUERY_KEYS.DOCUMENTS], (old) => {
        if (!old) return [];
        return old.filter((d) => d.id !== id);
      });

      // Optimistically remove from all conversation-scoped queries
      queryClient.setQueriesData<Document[]>(
        { queryKey: [QUERY_KEYS.DOCUMENTS, "conversation"] },
        (old) => {
          if (!old) return [];
          return old.filter((d) => d.id !== id);
        },
      );

      return { previousDocs };
    },
    onError: (_err, _id, context) => {
      if (context?.previousDocs) {
        queryClient.setQueryData([QUERY_KEYS.DOCUMENTS], context.previousDocs);
      }
      toast.error("Failed to delete document.");
    },
    onSuccess: () => {
      toast.success("Document deleted successfully.");
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEYS.DOCUMENTS] });
    },
  });
};

export const useReprocessDocument = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => documentsApi.reprocessDocument(id),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: [QUERY_KEYS.DOCUMENTS] });

      const previousDocs = queryClient.getQueryData<Document[]>([QUERY_KEYS.DOCUMENTS]);

      queryClient.setQueryData<Document[]>([QUERY_KEYS.DOCUMENTS], (old) => {
        if (!old) return [];
        return old.map((d) => (d.id === id ? { ...d, status: "pending" as const } : d));
      });

      return { previousDocs };
    },
    onError: (_err, _id, context) => {
      if (context?.previousDocs) {
        queryClient.setQueryData([QUERY_KEYS.DOCUMENTS], context.previousDocs);
      }
      toast.error("Failed to reprocess document.");
    },
    onSuccess: (data) => {
      toast.success(`Reprocessing started for "${data.original_filename}".`);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEYS.DOCUMENTS] });
    },
  });
};

export const useRegenerateEmbeddings = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => documentsApi.regenerateEmbeddings(id),
    onSuccess: (_data, id) => {
      // The regeneration job is queued; restart the embedding-status poll for
      // this document so a "failed" status (and the card banner) clears once
      // the job starts producing pending/generating rows.
      queryClient.invalidateQueries({
        queryKey: [QUERY_KEYS.EMBEDDING_STATUS, id],
      });
      toast.success("Embedding regeneration task queued.");
    },
    onError: (err) => {
      toast.error(`Failed to regenerate embeddings: ${err.message || err}`);
    },
  });
};

export const useReplaceDocument = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      file,
      onProgress,
      signal,
    }: {
      id: string;
      file: File;
      onProgress?: (progressEvent: unknown) => void;
      signal?: AbortSignal;
    }) => documentsApi.replaceDocument(id, file, onProgress, signal),
    onMutate: async ({ id, file }) => {
      await queryClient.cancelQueries({ queryKey: [QUERY_KEYS.DOCUMENTS] });

      const previousDocs = queryClient.getQueryData<Document[]>([QUERY_KEYS.DOCUMENTS]);

      queryClient.setQueryData<Document[]>([QUERY_KEYS.DOCUMENTS], (old) => {
        if (!old) return [];
        return old.map((d) =>
          d.id === id
            ? {
                ...d,
                original_filename: file.name,
                file_size: file.size,
                status: "pending" as const,
                updated_at: new Date().toISOString(),
              }
            : d,
        );
      });

      return { previousDocs };
    },
    onError: (err, _variables, context) => {
      if (context?.previousDocs) {
        queryClient.setQueryData([QUERY_KEYS.DOCUMENTS], context.previousDocs);
      }
      const isCancelled = err instanceof DOMException && err.name === "AbortError";
      if (!isCancelled) {
        toast.error(`Failed to replace document: ${(err as Error).message || err}`);
      }
    },
    onSuccess: (data) => {
      queryClient.setQueryData<Document[]>([QUERY_KEYS.DOCUMENTS], (old) => {
        if (!old) return [data];
        return old.map((d) => (d.id === data.id ? data : d));
      });
      queryClient.invalidateQueries({
        queryKey: [QUERY_KEYS.EMBEDDING_STATUS, data.id],
      });
      toast.success(`File "${data.original_filename}" replaced successfully.`);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEYS.DOCUMENTS] });
    },
  });
};
