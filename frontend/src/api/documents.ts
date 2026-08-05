import api from "./client";
import { Document, EmbeddingStatus } from "../types";

export const documentsApi = {
  async uploadDocument(
    file: File,
    onUploadProgress?: (progressEvent: unknown) => void,
    signal?: AbortSignal
  ): Promise<Document> {
    const formData = new FormData();
    formData.append("file", file);

    const response = await api.post<Document>("/documents/upload", formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
      onUploadProgress,
      signal,
    });
    return response.data;
  },

  async listDocuments(): Promise<Document[]> {
    const response = await api.get<Document[]>("/documents");
    return response.data;
  },

  async getDocument(id: string): Promise<Document> {
    const response = await api.get<Document>(`/documents/${id}`);
    return response.data;
  },

  async deleteDocument(id: string): Promise<void> {
    await api.delete(`/documents/${id}`);
  },

  async reprocessDocument(id: string): Promise<Document> {
    const response = await api.post<Document>(`/documents/${id}/reprocess`);
    return response.data;
  },

  async getEmbeddingStatus(id: string): Promise<EmbeddingStatus> {
    const response = await api.get<EmbeddingStatus>(`/documents/${id}/embeddings/status`);
    return response.data;
  },

  async regenerateEmbeddings(id: string): Promise<{ message: string }> {
    const response = await api.post<{ message: string }>(`/documents/${id}/embeddings/regenerate`);
    return response.data;
  },
};
