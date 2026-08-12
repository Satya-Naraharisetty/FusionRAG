import React, { useMemo, useState, useEffect } from "react";
import {
  useDocuments,
  useDeleteDocument,
  useReprocessDocument,
  useRegenerateEmbeddings,
} from "../hooks/useDocuments";
import { useEmbeddingStatus } from "../hooks/useEmbeddingStatus";
import { Document } from "../types";
import { UploadDropzone } from "../components/documents/UploadDropzone";
import {
  DocumentFilters,
  DocumentSortType,
  DocumentFilterType,
  DateRange,
} from "../components/documents/DocumentFilters";
import { DocumentGrid } from "../components/documents/DocumentGrid";
import { LayoutGrid, List, Download, Trash2, X, FolderOpen } from "lucide-react";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "../components/ui/Modal";
import toast from "react-hot-toast";

interface DocFolder {
  id: string;
  name: string;
}

const DocumentsPage: React.FC = () => {
  const { data: documents = [], isLoading, error } = useDocuments();
  const embeddingStatus     = useEmbeddingStatus();
  const deleteMutation       = useDeleteDocument();
  const reprocessMutation    = useReprocessDocument();
  const regenerateMutation   = useRegenerateEmbeddings();

  const [viewMode, setViewMode]     = useState<"grid" | "list">("grid");
  const [search, setSearch]         = useState("");
  const [sort, setSort]             = useState<DocumentSortType>("newest");
  const [filter, setFilter]         = useState<DocumentFilterType>("all");
  const [selectedFolderId, setSelectedFolderId]     = useState<string | null>(null);
  const [selectedLanguages, setSelectedLanguages]   = useState<string[]>([]);
  const [dateRange, setDateRange]   = useState<DateRange>({ start: "", end: "" });

  const [folders, setFolders] = useState<DocFolder[]>(() => {
    const saved = localStorage.getItem("document-folders");
    return saved
      ? JSON.parse(saved)
      : [
          { id: "folder-invoices",  name: "Invoices" },
          { id: "folder-contracts", name: "Contracts" },
          { id: "folder-reports",   name: "Reports" },
        ];
  });
  const [showNewFolderModal, setShowNewFolderModal] = useState(false);
  const [newFolderName, setNewFolderName]           = useState("");

  const [folderMappings, setFolderMappings] = useState<Record<string, string>>(() => {
    const saved = localStorage.getItem("document-folder-mappings");
    return saved ? JSON.parse(saved) : {};
  });

  const [customOrder, setCustomOrder] = useState<string[]>(() => {
    const saved = localStorage.getItem("document-custom-order");
    return saved ? JSON.parse(saved) : [];
  });

  const [presets, setPresets] = useState<Record<string, Record<string, unknown>>>(() => {
    const saved = localStorage.getItem("document-filter-presets");
    return saved ? JSON.parse(saved) : {};
  });

  const [selectedIds, setSelectedIds]   = useState<string[]>([]);
  const [draggedDocId, setDraggedDocId] = useState<string | null>(null);

  // Persist to localStorage
  useEffect(() => { localStorage.setItem("document-folders", JSON.stringify(folders)); }, [folders]);
  useEffect(() => { localStorage.setItem("document-folder-mappings", JSON.stringify(folderMappings)); }, [folderMappings]);
  useEffect(() => { localStorage.setItem("document-custom-order", JSON.stringify(customOrder)); }, [customOrder]);
  useEffect(() => { localStorage.setItem("document-filter-presets", JSON.stringify(presets)); }, [presets]);

  const availableLanguages = useMemo(() => {
    const langs = new Set<string>();
    documents.forEach((d) => { if (d.language) langs.add(d.language.toLowerCase()); });
    return Array.from(langs);
  }, [documents]);

  const handleCreateFolder = () => {
    const name = newFolderName.trim();
    if (!name) return;
    setFolders((prev) => [...prev, { id: `doc-folder-${Math.random().toString(36).substring(2, 9)}`, name }]);
    setNewFolderName("");
    setShowNewFolderModal(false);
    toast.success(`Created folder "${name}"`);
  };

  const handleClearAllFilters = () => {
    setSearch(""); setSort("newest"); setFilter("all");
    setSelectedFolderId(null); setSelectedLanguages([]); setDateRange({ start: "", end: "" });
  };

  const handleSelectToggle   = (id: string) =>
    setSelectedIds((prev) => prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]);

  const handleSelectAllToggle = (visibleDocs: Document[]) => {
    const ids = visibleDocs.map((d) => d.id);
    const allSelected = ids.every((id) => selectedIds.includes(id));
    setSelectedIds((prev) =>
      allSelected ? prev.filter((id) => !ids.includes(id)) : Array.from(new Set([...prev, ...ids]))
    );
  };

  const filteredAndSortedDocs = useMemo(() => {
    let result = [...documents];

    if (filter === "chat") result = result.filter((d) => d.conversation_id !== null);
    else if (filter !== "all") result = result.filter((d) => d.status === filter);

    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (d) => d.original_filename.toLowerCase().includes(q) || d.filename.toLowerCase().includes(q)
      );
    }

    if (selectedFolderId !== null) result = result.filter((d) => folderMappings[d.id] === selectedFolderId);
    if (selectedLanguages.length > 0)
      result = result.filter((d) => d.language && selectedLanguages.includes(d.language.toLowerCase()));
    if (dateRange.start) {
      const start = new Date(dateRange.start).getTime();
      result = result.filter((d) => new Date(d.created_at).getTime() >= start);
    }
    if (dateRange.end) {
      const end = new Date(dateRange.end).getTime() + 86400000;
      result = result.filter((d) => new Date(d.created_at).getTime() <= end);
    }

    result.sort((a, b) => {
      if (sort === "newest") return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      if (sort === "oldest") return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      if (sort === "name")   return a.original_filename.localeCompare(b.original_filename);
      if (sort === "status") return a.status.localeCompare(b.status);
      if (sort === "size")   return b.file_size - a.file_size;
      return 0;
    });

    if (customOrder.length > 0) {
      const orderMap = new Map(customOrder.map((id, i) => [id, i]));
      result.sort((a, b) => (orderMap.get(a.id) ?? 99999) - (orderMap.get(b.id) ?? 99999));
    }

    return result;
  }, [documents, search, sort, filter, selectedFolderId, selectedLanguages, dateRange, folderMappings, customOrder]);

  const handleBulkDelete = async () => {
    if (!window.confirm(`Delete ${selectedIds.length} selected file(s)?`)) return;
    const id = toast.loading("Deleting…");
    try {
      await Promise.all(selectedIds.map((sid) => deleteMutation.mutateAsync(sid)));
      setSelectedIds([]);
      toast.success("Files deleted.", { id });
    } catch {
      toast.error("Failed to delete some files.", { id });
    }
  };

  const handleBulkMoveToFolder = (folderId: string | null) => {
    setFolderMappings((prev) => {
      const updated = { ...prev };
      selectedIds.forEach((id) => {
        if (folderId === null) delete updated[id];
        else updated[id] = folderId;
      });
      return updated;
    });
    setSelectedIds([]);
    toast.success("Moved to folder.");
  };

  const handleBulkExport = () => {
    toast.success(`Exported ${selectedIds.length} file(s).`);
    setSelectedIds([]);
  };

  const handleDragStart = (id: string) => setDraggedDocId(id);
  const handleDragOver  = (e: React.DragEvent) => e.preventDefault();
  const handleDrop      = (targetId: string) => {
    if (!draggedDocId || draggedDocId === targetId) return;
    const newOrder = customOrder.length > 0 ? [...customOrder] : documents.map((d) => d.id);
    const fromIdx = newOrder.indexOf(draggedDocId);
    const toIdx   = newOrder.indexOf(targetId);
    if (fromIdx !== -1 && toIdx !== -1) {
      newOrder.splice(fromIdx, 1);
      newOrder.splice(toIdx, 0, draggedDocId);
      setCustomOrder(newOrder);
    }
    setDraggedDocId(null);
  };

  return (
    <div className="flex-1 overflow-y-auto bg-(--bg-primary) text-(--text-primary)">
      <div className="max-w-4xl mx-auto px-4 py-8 md:px-8 space-y-6 relative pb-20">

        {/* ── Page header ── */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-(--text-primary)">
              Documents
            </h1>
            <p className="mt-1 text-sm text-(--text-secondary)">
              Manage your knowledge base. Upload documents to query them in chat.
            </p>
          </div>

          {/* View toggle + new folder */}
          <div className="flex items-center gap-2 shrink-0">
            <Button
              variant="ghost"
              size="iconSm"
              onClick={() => setShowNewFolderModal(true)}
              title="New folder"
              aria-label="Create new folder"
            >
              <FolderOpen size={15} />
            </Button>
            <div className="flex items-center rounded-md border border-(--border-subtle) bg-(--bg-tertiary) p-0.5">
              <button
                onClick={() => setViewMode("grid")}
                className={`cursor-pointer rounded-sm p-1.5 transition-colors ${
                  viewMode === "grid"
                    ? "bg-(--bg-elevated) text-(--text-primary)"
                    : "text-(--text-muted) hover:text-(--text-primary)"
                }`}
                title="Grid view"
                aria-label="Switch to grid view"
                data-active={viewMode === "grid"}
              >
                <LayoutGrid size={13} />
              </button>
              <button
                onClick={() => setViewMode("list")}
                className={`cursor-pointer rounded-sm p-1.5 transition-colors ${
                  viewMode === "list"
                    ? "bg-(--bg-elevated) text-(--text-primary)"
                    : "text-(--text-muted) hover:text-(--text-primary)"
                }`}
                title="List view"
                aria-label="Switch to list view"
                data-active={viewMode === "list"}
              >
                <List size={13} />
              </button>
            </div>
          </div>
        </div>

        {/* ── Upload dropzone ── */}
        <UploadDropzone />

        {/* ── Filters ── */}
        <DocumentFilters
          search={search}
          onSearchChange={setSearch}
          sort={sort}
          onSortChange={setSort}
          filter={filter}
          onFilterChange={setFilter}
          totalCount={documents.length}
          filteredCount={filteredAndSortedDocs.length}
          selectedFolderId={selectedFolderId}
          onSelectedFolderChange={setSelectedFolderId}
          folders={folders}
          selectedLanguages={selectedLanguages}
          onSelectedLanguagesChange={setSelectedLanguages}
          availableLanguages={availableLanguages}
          dateRange={dateRange}
          onDateRangeChange={setDateRange}
          onClearAll={handleClearAllFilters}
          savedPresets={presets}
          onSavePreset={(name) => {
            setPresets((prev) => ({
              ...prev,
              [name]: { search, sort, filter, selectedFolderId, selectedLanguages, dateRange },
            }));
            toast.success(`Saved preset "${name}"`);
          }}
          onDeletePreset={(name) => {
            setPresets((prev) => { const u = { ...prev }; delete u[name]; return u; });
            toast.success(`Deleted preset "${name}"`);
          }}
          onLoadPreset={(name) => {
            const p = presets[name];
            if (!p) return;
            setSearch((p.search as string) || "");
            setSort((p.sort as DocumentSortType) || "newest");
            setFilter((p.filter as DocumentFilterType) || "all");
            setSelectedFolderId((p.selectedFolderId as string | null) || null);
            setSelectedLanguages((p.selectedLanguages as string[]) || []);
            setDateRange((p.dateRange as DateRange) || { start: "", end: "" });
            toast.success(`Loaded preset "${name}"`);
          }}
        />

        {/* ── Document grid / list ── */}
        <DocumentGrid
          filteredAndSortedDocs={filteredAndSortedDocs}
          embeddingStatus={embeddingStatus}
          isLoading={isLoading}
          error={error}
          viewMode={viewMode}
          selectedIds={selectedIds}
          handleSelectToggle={handleSelectToggle}
          handleSelectAllToggle={handleSelectAllToggle}
          onDelete={async (id) => deleteMutation.mutateAsync(id)}
          onReprocess={async (id) => reprocessMutation.mutateAsync(id)}
          onRegenerateEmbeddings={async (id) => regenerateMutation.mutateAsync(id)}
          folders={folders}
          folderMappings={folderMappings}
          setFolderMappings={setFolderMappings}
          handleDragStart={handleDragStart}
          handleDragOver={handleDragOver}
          handleDrop={handleDrop}
          search={search}
          filter={filter}
          selectedFolderId={selectedFolderId}
          selectedLanguages={selectedLanguages}
          dateRange={dateRange}
        />

        {/* ── Bulk action bar ── */}
        {selectedIds.length > 0 && (
          <div
            className="fixed bottom-6 left-1/2 z-40 flex -translate-x-1/2 items-center gap-3 rounded-pill border border-(--border-default) bg-(--bg-elevated) px-5 py-2.5 shadow-md animate-in slide-in-from-bottom duration-200"
            role="toolbar"
            aria-label="Bulk actions"
          >
            <span className="border-r border-(--border-subtle) pr-3 text-xs font-medium text-(--text-secondary) select-none">
              {selectedIds.length} selected
            </span>

            <div className="flex items-center gap-2">
              <select
                onChange={(e) => {
                  const val = e.target.value;
                  if (val === "none") handleBulkMoveToFolder(null);
                  else if (val)       handleBulkMoveToFolder(val);
                  e.target.value = "";
                }}
                className="h-8 cursor-pointer rounded-md border border-(--border-default) bg-(--bg-input) px-2 text-xs text-(--text-primary) outline-none transition-colors focus:border-(--accent-primary)/50"
                aria-label="Move selected to folder"
                title="Move selected to folder"
              >
                <option value="">Move to folder…</option>
                <option value="none">No folder</option>
                {folders.map((f) => (
                  <option key={f.id} value={f.id}>{f.name}</option>
                ))}
              </select>

              <Button size="sm" variant="secondary" onClick={handleBulkExport} className="h-8 gap-1.5">
                <Download size={12} />
                Export
              </Button>

              <Button size="sm" variant="destructive" onClick={handleBulkDelete} className="h-8 gap-1.5">
                <Trash2 size={12} />
                Delete
              </Button>

              <button
                type="button"
                onClick={() => setSelectedIds([])}
                className="cursor-pointer p-1 text-(--text-muted) transition-colors hover:text-(--text-primary)"
                title="Clear selection"
                aria-label="Clear selection"
              >
                <X size={14} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── New Folder dialog ── */}
      <Dialog open={showNewFolderModal} onOpenChange={setShowNewFolderModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-sm">
              <FolderOpen size={15} className="text-(--accent-primary)" />
              <span>Create Folder</span>
            </DialogTitle>
          </DialogHeader>
          <div className="py-2">
            <Input
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="e.g. Legal, Finance, Reports"
              onKeyDown={(e) => { if (e.key === "Enter") handleCreateFolder(); }}
              autoFocus
            />
          </div>
          <DialogFooter className="gap-2">
            <Button variant="secondary" size="sm" onClick={() => setShowNewFolderModal(false)}>
              Cancel
            </Button>
            <Button variant="default" size="sm" onClick={handleCreateFolder}>
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default DocumentsPage;
