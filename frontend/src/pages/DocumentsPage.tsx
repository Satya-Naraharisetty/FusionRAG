import React, { useMemo, useState } from "react";
import {
  useDocuments,
  useDeleteDocument,
  useReprocessDocument,
  useRegenerateEmbeddings,
} from "../hooks/useDocuments";
import { UploadDropzone } from "../components/documents/UploadDropzone";
import { DocumentFilters, DocumentSortType, DocumentFilterType } from "../components/documents/DocumentFilters";
import { DocumentCard } from "../components/documents/DocumentCard";
import { AlertCircle, FileText } from "lucide-react";
import { Skeleton } from "../components/ui/skeleton";

const DocumentsPage: React.FC = () => {
  const { data: documents = [], isLoading, error } = useDocuments();

  const deleteMutation = useDeleteDocument();
  const reprocessMutation = useReprocessDocument();
  const regenerateMutation = useRegenerateEmbeddings();

  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<DocumentSortType>("newest");
  const [filter, setFilter] = useState<DocumentFilterType>("all");

  const filteredAndSortedDocs = useMemo(() => {
    let result = [...documents];

    // Filter by status tab
    if (filter !== "all") {
      result = result.filter((d) => d.status === filter);
    }

    // Filter by search query
    if (search.trim()) {
      const query = search.toLowerCase();
      result = result.filter(
        (d) =>
          d.original_filename.toLowerCase().includes(query) ||
          d.filename.toLowerCase().includes(query)
      );
    }

    // Sort
    result.sort((a, b) => {
      if (sort === "newest") {
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }
      if (sort === "oldest") {
        return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      }
      if (sort === "name") {
        return a.original_filename.localeCompare(b.original_filename);
      }
      if (sort === "status") {
        return a.status.localeCompare(b.status);
      }
      return 0;
    });

    return result;
  }, [documents, search, sort, filter]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 md:p-8 bg-zinc-950 scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="space-y-1">
          <h1 className="text-lg font-bold font-title text-zinc-100 flex items-center gap-2">
            <FileText size={18} className="text-violet-500" />
            <span>Document Repository</span>
          </h1>
          <p className="text-xs text-zinc-500">
            Upload files to build your knowledge base and query them during chats.
          </p>
        </div>

        {/* Dropzone area */}
        <UploadDropzone />

        {/* Filters and count */}
        <DocumentFilters
          search={search}
          onSearchChange={setSearch}
          sort={sort}
          onSortChange={setSort}
          filter={filter}
          onFilterChange={setFilter}
          totalCount={documents.length}
          filteredCount={filteredAndSortedDocs.length}
        />

        {/* Main List Grid */}
        {isLoading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, idx) => (
              <div key={idx} className="h-40 bg-zinc-900/40 border border-zinc-850 rounded-xl p-4 space-y-4">
                <div className="flex items-center gap-3">
                  <Skeleton className="h-8 w-8 rounded-lg bg-zinc-850" />
                  <div className="space-y-2 flex-1">
                    <Skeleton className="h-3 w-3/4 bg-zinc-850" />
                    <Skeleton className="h-2 w-1/4 bg-zinc-850" />
                  </div>
                </div>
                <div className="space-y-2">
                  <Skeleton className="h-2 w-full bg-zinc-850" />
                  <Skeleton className="h-2 w-2/3 bg-zinc-850" />
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center p-8 text-center text-red-400">
            <AlertCircle size={24} className="mb-2" />
            <p className="text-xs font-semibold">Failed to fetch document library.</p>
          </div>
        ) : filteredAndSortedDocs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 px-4 text-center border border-zinc-900 border-dashed rounded-2xl">
            <FileText size={32} className="text-zinc-700 mb-2" />
            <span className="text-xs font-bold text-zinc-400">No documents found</span>
            <p className="text-[10px] text-zinc-650 max-w-xs mt-1">
              {search || filter !== "all"
                ? "Try adjusting your filters or search terms."
                : "Upload PDF or text documents to start indexing."}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
            {filteredAndSortedDocs.map((doc) => (
              <DocumentCard
                key={doc.id}
                document={doc}
                onDelete={async (id) => deleteMutation.mutateAsync(id)}
                onReprocess={async (id) => reprocessMutation.mutateAsync(id)}
                onRegenerateEmbeddings={async (id) => regenerateMutation.mutateAsync(id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default DocumentsPage;
