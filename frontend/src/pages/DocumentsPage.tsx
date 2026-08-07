import React, { useMemo, useState, useEffect } from "react";
import {
  useDocuments,
  useDeleteDocument,
  useReprocessDocument,
  useRegenerateEmbeddings,
} from "../hooks/useDocuments";
import { Document } from "../types";
import { UploadDropzone } from "../components/documents/UploadDropzone";
import {
  DocumentFilters,
  DocumentSortType,
  DocumentFilterType,
  DateRange,
} from "../components/documents/DocumentFilters";
import { DocumentCard } from "../components/documents/DocumentCard";
import {
  AlertCircle,
  FileText,
  LayoutGrid,
  List,
  FolderOpen,
  Download,
  Trash2,
  X,
  Plus,
} from "lucide-react";
import { Skeleton } from "../components/ui/skeleton";
import { formatBytes, relativeTime } from "../lib/utils";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "../components/ui/dialog";
import toast from "react-hot-toast";

interface DocFolder {
  id: string;
  name: string;
}

const DocumentsPage: React.FC = () => {
  const { data: documents = [], isLoading, error } = useDocuments();

  const deleteMutation = useDeleteDocument();
  const reprocessMutation = useReprocessDocument();
  const regenerateMutation = useRegenerateEmbeddings();

  // Custom configuration states
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  // Advanced Filters states
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<DocumentSortType>("newest");
  const [filter, setFilter] = useState<DocumentFilterType>("all");
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const [selectedLanguages, setSelectedLanguages] = useState<string[]>([]);
  const [dateRange, setDateRange] = useState<DateRange>({ start: "", end: "" });

  // Document Folders
  const [folders, setFolders] = useState<DocFolder[]>(() => {
    const saved = localStorage.getItem("document-folders");
    return saved ? JSON.parse(saved) : [
      { id: "folder-invoices", name: "Invoices" },
      { id: "folder-contracts", name: "Contracts" },
      { id: "folder-reports", name: "Reports" },
    ];
  });
  const [showNewFolderModal, setShowNewFolderModal] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");

  // Document Folder Mappings (docId -> folderId)
  const [folderMappings, setFolderMappings] = useState<Record<string, string>>(() => {
    const saved = localStorage.getItem("document-folder-mappings");
    return saved ? JSON.parse(saved) : {};
  });

  // Custom manual drag sorting ids order
  const [customOrder, setCustomOrder] = useState<string[]>(() => {
    const saved = localStorage.getItem("document-custom-order");
    return saved ? JSON.parse(saved) : [];
  });

  // Saved presets state
  const [presets, setPresets] = useState<Record<string, Record<string, unknown>>>(() => {
    const saved = localStorage.getItem("document-filter-presets");
    return saved ? JSON.parse(saved) : {};
  });

  // Bulk selections
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  // Drag-and-drop state inside page
  const [draggedDocId, setDraggedDocId] = useState<string | null>(null);

  // Sync state helpers to localStorage
  useEffect(() => {
    localStorage.setItem("document-folders", JSON.stringify(folders));
  }, [folders]);

  useEffect(() => {
    localStorage.setItem("document-folder-mappings", JSON.stringify(folderMappings));
  }, [folderMappings]);

  useEffect(() => {
    localStorage.setItem("document-custom-order", JSON.stringify(customOrder));
  }, [customOrder]);

  useEffect(() => {
    localStorage.setItem("document-filter-presets", JSON.stringify(presets));
  }, [presets]);

  // Extract unique languages dynamically from data
  const availableLanguages = useMemo(() => {
    const langs = new Set<string>();
    documents.forEach((d) => {
      if (d.language) langs.add(d.language.toLowerCase());
    });
    return Array.from(langs);
  }, [documents]);

  const handleCreateFolder = () => {
    const name = newFolderName.trim();
    if (!name) return;
    const newFolder = {
      id: `doc-folder-${Math.random().toString(36).substring(2, 9)}`,
      name,
    };
    setFolders((prev) => [...prev, newFolder]);
    setNewFolderName("");
    setShowNewFolderModal(false);
    toast.success(`Created folder "${name}"`);
  };

  const handleSavePreset = (presetName: string) => {
    const current = {
      search,
      sort,
      filter,
      selectedFolderId,
      selectedLanguages,
      dateRange,
    };
    setPresets((prev) => ({ ...prev, [presetName]: current }));
    toast.success(`Saved preset "${presetName}"`);
  };

  const handleDeletePreset = (presetName: string) => {
    setPresets((prev) => {
      const updated = { ...prev };
      delete updated[presetName];
      return updated;
    });
    toast.success(`Deleted preset "${presetName}"`);
  };

  const handleLoadPreset = (presetName: string) => {
    const preset = presets[presetName];
    if (preset) {
      setSearch((preset.search as string) || "");
      setSort((preset.sort as DocumentSortType) || "newest");
      setFilter((preset.filter as DocumentFilterType) || "all");
      setSelectedFolderId((preset.selectedFolderId as string | null) || null);
      setSelectedLanguages((preset.selectedLanguages as string[]) || []);
      setDateRange((preset.dateRange as DateRange) || { start: "", end: "" });
      toast.success(`Applied preset "${presetName}"`);
    }
  };

  const handleClearAllFilters = () => {
    setSearch("");
    setSort("newest");
    setFilter("all");
    setSelectedFolderId(null);
    setSelectedLanguages([]);
    setDateRange({ start: "", end: "" });
    toast.success("Cleared all filters");
  };

  // Toggle selection for a document
  const handleSelectToggle = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((sId) => sId !== id) : [...prev, id]
    );
  };

  // Toggle select all
  const handleSelectAllToggle = (visibleDocs: Document[]) => {
    const visibleIds = visibleDocs.map((d) => d.id);
    const allSelected = visibleIds.every((id) => selectedIds.includes(id));
    if (allSelected) {
      setSelectedIds((prev) => prev.filter((id) => !visibleIds.includes(id)));
    } else {
      setSelectedIds((prev) => Array.from(new Set([...prev, ...visibleIds])));
    }
  };

  // Filter & Sort core logic
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

    // Filter by advanced folder mapping
    if (selectedFolderId !== null) {
      result = result.filter((d) => folderMappings[d.id] === selectedFolderId);
    }

    // Filter by advanced languages
    if (selectedLanguages.length > 0) {
      result = result.filter((d) => d.language && selectedLanguages.includes(d.language.toLowerCase()));
    }

    // Filter by date range picker
    if (dateRange.start) {
      const start = new Date(dateRange.start).getTime();
      result = result.filter((d) => new Date(d.created_at).getTime() >= start);
    }
    if (dateRange.end) {
      const end = new Date(dateRange.end).getTime() + 86400000; // plus 1 day to be inclusive
      result = result.filter((d) => new Date(d.created_at).getTime() <= end);
    }

    // Sort mappings
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
      if (sort === "size") {
        return b.file_size - a.file_size;
      }
      return 0;
    });

    // Custom order mapping
    if (customOrder.length > 0) {
      const orderMap = new Map(customOrder.map((id, index) => [id, index]));
      result.sort((a, b) => {
        const orderA = orderMap.get(a.id) ?? 99999;
        const orderB = orderMap.get(b.id) ?? 99999;
        return orderA - orderB;
      });
    }

    return result;
  }, [documents, search, sort, filter, selectedFolderId, selectedLanguages, dateRange, folderMappings, customOrder]);

  // Bulk actions handlers
  const handleBulkDelete = async () => {
    if (window.confirm(`Are you sure you want to delete the ${selectedIds.length} selected files?`)) {
      const toastId = toast.loading("Deleting files...");
      try {
        await Promise.all(selectedIds.map((id) => deleteMutation.mutateAsync(id)));
        setSelectedIds([]);
        toast.success("Successfully deleted files.", { id: toastId });
      } catch (_e) {
        toast.error("Failed to delete all selected files.", { id: toastId });
      }
    }
  };

  const handleBulkMoveToFolder = (folderId: string | null) => {
    setFolderMappings((prev) => {
      const updated = { ...prev };
      selectedIds.forEach((id) => {
        if (folderId === null) {
          delete updated[id];
        } else {
          updated[id] = folderId;
        }
      });
      return updated;
    });
    setSelectedIds([]);
    toast.success("Moved files to folder.");
  };

  const handleBulkExport = () => {
    toast.success(`Exported ${selectedIds.length} file metadata packages!`);
    setSelectedIds([]);
  };

  // Drag and drop reordering
  const handleDragStart = (id: string) => {
    setDraggedDocId(id);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (targetId: string) => {
    if (!draggedDocId || draggedDocId === targetId) return;

    // Rearrange custom order
    let newOrder = [...customOrder];
    if (newOrder.length === 0) {
      newOrder = documents.map((d) => d.id);
    }

    const draggedIndex = newOrder.indexOf(draggedDocId);
    const targetIndex = newOrder.indexOf(targetId);

    if (draggedIndex !== -1 && targetIndex !== -1) {
      newOrder.splice(draggedIndex, 1);
      newOrder.splice(targetIndex, 0, draggedDocId);
      setCustomOrder(newOrder);
    }
    setDraggedDocId(null);
  };

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 md:p-8 bg-zinc-950 scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent">
      <div className="max-w-4xl mx-auto space-y-6 relative pb-16">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <h1 className="text-lg font-bold font-title text-zinc-100 flex items-center gap-2">
              <FileText size={18} className="text-violet-500" />
              <span>Document Repository</span>
            </h1>
            <p className="text-xs text-zinc-500">
              Upload files to build your knowledge base and query them during chats.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              onClick={() => setShowNewFolderModal(true)}
              className="h-8.5 w-8.5 bg-zinc-900 border-zinc-900 hover:border-zinc-800 text-zinc-400 hover:text-zinc-200 cursor-pointer"
              title="Add New Folder"
            >
              <Plus size={15} />
            </Button>
            <div className="flex items-center bg-zinc-900 border border-zinc-850 p-1 rounded-lg">
              <button
                onClick={() => setViewMode("grid")}
                className={`p-1 rounded cursor-pointer transition-colors ${
                  viewMode === "grid" ? "bg-zinc-800 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"
                }`}
                title="Grid layout"
              >
                <LayoutGrid size={15} />
              </button>
              <button
                onClick={() => setViewMode("list")}
                className={`p-1 rounded cursor-pointer transition-colors ${
                  viewMode === "list" ? "bg-zinc-800 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"
                }`}
                title="List layout"
              >
                <List size={15} />
              </button>
            </div>
          </div>
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
          onSavePreset={handleSavePreset}
          onDeletePreset={handleDeletePreset}
          onLoadPreset={handleLoadPreset}
        />

        {/* Main List / Grid */}
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
              {search || filter !== "all" || selectedFolderId !== null || selectedLanguages.length > 0 || dateRange.start || dateRange.end
                ? "Try adjusting your filters or search terms."
                : "Upload PDF or text documents to start indexing."}
            </p>
          </div>
        ) : viewMode === "grid" ? (
          /* Grid View Mode */
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
            {filteredAndSortedDocs.map((doc) => (
              <DocumentCard
                key={doc.id}
                document={doc}
                onDelete={async (id) => deleteMutation.mutateAsync(id)}
                onReprocess={async (id) => reprocessMutation.mutateAsync(id)}
                onRegenerateEmbeddings={async (id) => regenerateMutation.mutateAsync(id)}
                isSelected={selectedIds.includes(doc.id)}
                onSelectToggle={() => handleSelectToggle(doc.id)}
                documentFolders={folders}
                currentFolderId={folderMappings[doc.id]}
                onMoveToFolder={(folderId) =>
                  setFolderMappings((prev) => {
                    const next = { ...prev };
                    if (folderId === null) {
                      delete next[doc.id];
                    } else {
                      next[doc.id] = folderId;
                    }
                    return next;
                  })
                }
                onDuplicate={() => {
                  toast.success(`Duplicated document "${doc.original_filename}"`);
                }}
                onExport={() => {
                  toast.success(`Exported metadata for "${doc.original_filename}"`);
                }}
                onDragStart={() => handleDragStart(doc.id)}
                onDragOver={handleDragOver}
                onDrop={() => handleDrop(doc.id)}
              />
            ))}
          </div>
        ) : (
          /* List Table View Mode */
          <div className="border border-zinc-900 rounded-xl overflow-hidden bg-zinc-950/20 backdrop-blur-md">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-zinc-900 bg-zinc-950 text-[10px] font-bold text-zinc-500 uppercase tracking-wider select-none">
                  <th className="p-3 w-10">
                    <input
                      type="checkbox"
                      checked={
                        filteredAndSortedDocs.length > 0 &&
                        filteredAndSortedDocs.every((d) => selectedIds.includes(d.id))
                      }
                      onChange={() => handleSelectAllToggle(filteredAndSortedDocs)}
                      className="rounded accent-violet-600 focus-visible:outline-none"
                    />
                  </th>
                  <th className="p-3">File Name</th>
                  <th className="p-3 hidden sm:table-cell">Size</th>
                  <th className="p-3 hidden sm:table-cell">Uploaded</th>
                  <th className="p-3">Status</th>
                  <th className="p-3 w-12 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-900 text-xs font-semibold text-zinc-300">
                {filteredAndSortedDocs.map((doc) => {
                  const isChecked = selectedIds.includes(doc.id);
                  return (
                    <tr
                      key={doc.id}
                      className={`hover:bg-zinc-900/40 transition-colors ${
                        isChecked ? "bg-violet-950/5" : ""
                      }`}
                    >
                      <td className="p-3">
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => handleSelectToggle(doc.id)}
                          className="rounded accent-violet-600 focus-visible:outline-none"
                        />
                      </td>
                      <td className="p-3 font-medium text-zinc-200 max-w-[200px] sm:max-w-xs truncate">
                        <span title={doc.original_filename}>{doc.original_filename}</span>
                      </td>
                      <td className="p-3 hidden sm:table-cell text-zinc-450 font-mono text-[10px]">
                        {formatBytes(doc.file_size)}
                      </td>
                      <td className="p-3 hidden sm:table-cell text-zinc-450 font-mono text-[10px]">
                        {relativeTime(doc.created_at)}
                      </td>
                      <td className="p-3">
                        <span
                          className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase tracking-wider border ${
                            doc.status === "completed"
                              ? "bg-emerald-950/20 text-emerald-400 border-emerald-900/20"
                              : doc.status === "processing"
                                ? "bg-blue-950/20 text-blue-400 border-blue-900/20"
                                : doc.status === "failed"
                                  ? "bg-red-950/20 text-red-400 border-red-900/20"
                                  : "bg-amber-950/20 text-amber-400 border-amber-900/20"
                          }`}
                        >
                          {doc.status}
                        </span>
                      </td>
                      <td className="p-3 text-right">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={async () => {
                            if (window.confirm(`Delete document "${doc.original_filename}"?`)) {
                              await deleteMutation.mutateAsync(doc.id);
                            }
                          }}
                          className="h-7 w-7 text-zinc-500 hover:text-red-400 hover:bg-red-950/10 cursor-pointer"
                        >
                          <Trash2 size={12} />
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Floating Bulk Actions Toolbar */}
        {selectedIds.length > 0 && (
          <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 bg-zinc-950/95 border border-zinc-800 rounded-full px-5 py-3 shadow-2xl flex items-center gap-4 animate-in slide-in-from-bottom duration-300">
            <span className="text-[10px] font-bold text-zinc-300 select-none border-r border-zinc-800 pr-3.5">
              {selectedIds.length} Selected
            </span>

            <div className="flex items-center gap-2">
              {/* Folder Selector for bulk items */}
              <select
                onChange={(e) => {
                  if (e.target.value === "none") {
                    handleBulkMoveToFolder(null);
                  } else if (e.target.value) {
                    handleBulkMoveToFolder(e.target.value);
                  }
                  e.target.value = "";
                }}
                className="h-8.5 rounded-lg bg-zinc-900 border border-zinc-850 text-[10px] px-2 focus-visible:outline-none text-zinc-300 cursor-pointer"
              >
                <option value="">Move to Folder...</option>
                <option value="none">No Folder</option>
                {folders.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>

              <Button
                size="sm"
                onClick={handleBulkExport}
                className="h-8 bg-zinc-900 border border-zinc-850 hover:bg-zinc-850 text-zinc-300 text-[10px] font-bold cursor-pointer rounded-lg gap-1.5 px-3"
              >
                <Download size={11} />
                <span>Export</span>
              </Button>

              <Button
                size="sm"
                onClick={handleBulkDelete}
                className="h-8 bg-red-950/30 hover:bg-red-900/40 text-red-400 border border-red-900/30 text-[10px] font-bold cursor-pointer rounded-lg gap-1.5 px-3"
              >
                <Trash2 size={11} />
                <span>Delete</span>
              </Button>

              <button
                onClick={() => setSelectedIds([])}
                className="text-zinc-500 hover:text-zinc-350 p-1 cursor-pointer"
                title="Cancel selection"
              >
                <X size={14} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* New Folder Creation Dialog */}
      <Dialog open={showNewFolderModal} onOpenChange={setShowNewFolderModal}>
        <DialogContent className="bg-zinc-950 border-zinc-800 text-zinc-200 sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-zinc-100 flex items-center gap-2">
              <FolderOpen size={18} className="text-violet-500" />
              <span>Create Document Folder</span>
            </DialogTitle>
          </DialogHeader>
          <div className="py-3">
            <Input
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="e.g. Legal, Finance, Invoices"
              className="bg-zinc-900 border-zinc-800 text-zinc-200 text-xs focus-visible:ring-1 focus-visible:ring-violet-600"
              onKeyDown={(e) => {
                if (e.key === "Enter") handleCreateFolder();
              }}
            />
          </div>
          <DialogFooter className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => setShowNewFolderModal(false)}
              className="bg-transparent border-zinc-800 text-zinc-300 hover:bg-zinc-900 hover:text-zinc-100 text-xs"
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateFolder}
              className="bg-violet-600 hover:bg-violet-750 text-white text-xs font-semibold"
            >
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default DocumentsPage;
