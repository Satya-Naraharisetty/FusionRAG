import api, { getAccessToken } from "./client";
import { Document, EmbeddingStatus } from "../types";

const BASE_URL =
  (import.meta.env.VITE_API_URL || "http://localhost:8000") + "/api/v1";

/**
 * Upload via XMLHttpRequest: fetch has no upload-progress events, and the
 * UI drives a progress bar off onProgress. Rejects with a DOMException
 * AbortError when `signal` aborts (matches the callers' cancellation check).
 */
function uploadWithProgress(
  path: string,
  formData: FormData,
  onProgress?: (progressEvent: { loaded: number; total: number }) => void,
  signal?: AbortSignal
): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", BASE_URL + path);
    xhr.withCredentials = true;
    const token = getAccessToken();
    if (token) {
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }
    // Unlike the fetch path there is no 401-token-refresh retry here; the
    // AuthContext timer rotates tokens before expiry, so a stale-token upload
    // is rare. Rejecting with AbortError matches the callers' cancellation check.
    if (signal) {
      const abort = () => xhr.abort();
      signal.addEventListener("abort", abort, { once: true });
      // Don't leak the listener if the request settles normally.
      const cleanup = () => signal.removeEventListener("abort", abort);
      xhr.addEventListener("load", cleanup);
      xhr.addEventListener("error", cleanup);
      xhr.addEventListener("abort", cleanup);
    }
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress({ loaded: e.loaded, total: e.total });
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          resolve(null);
        }
      } else {
        let data: unknown;
        try {
          data = JSON.parse(xhr.responseText);
        } catch {
          data = undefined;
        }
        const message =
          (data as { message?: string } | null)?.message ||
          (data as { error?: { message?: string } } | null)?.error?.message ||
          `HTTP ${xhr.status}`;
        const err = new Error(message) as Error & { status: number; data: unknown };
        err.status = xhr.status;
        err.data = data;
        reject(err);
      }
    };
    xhr.onerror = () => reject(new Error("Network error"));
    xhr.onabort = () => {
      reject(new DOMException("The user aborted a request.", "AbortError"));
    };
    xhr.send(formData);
  });
}

export const documentsApi = {
  uploadDocument(
    file: File,
    onUploadProgress?: (progressEvent: unknown) => void,
    signal?: AbortSignal
  ): Promise<Document> {
    const formData = new FormData();
    formData.append("file", file);
    // (unknown) => void is assignable to ({loaded,total}) => void, so no cast needed.
    return uploadWithProgress(
      "/documents/upload",
      formData,
      onUploadProgress,
      signal
    ) as Promise<Document>;
  },

  listDocuments(): Promise<Document[]> {
    return api.get<Document[]>("/documents");
  },

  getDocument(id: string): Promise<Document> {
    return api.get<Document>(`/documents/${id}`);
  },

  deleteDocument(id: string): Promise<void> {
    return api.delete(`/documents/${id}`);
  },

  reprocessDocument(id: string): Promise<Document> {
    return api.post<Document>(`/documents/${id}/reprocess`);
  },

  getEmbeddingStatus(id: string): Promise<EmbeddingStatus> {
    return api.get<EmbeddingStatus>(`/documents/${id}/embeddings/status`);
  },

  regenerateEmbeddings(id: string): Promise<{ message: string }> {
    return api.post<{ message: string }>(`/documents/${id}/embeddings/regenerate`);
  },
};
