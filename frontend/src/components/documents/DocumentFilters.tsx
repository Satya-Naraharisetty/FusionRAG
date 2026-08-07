import React, { useState } from "react";
import { Search, X, FolderOpen, Calendar, Filter, Save, Trash2 } from "lucide-react";
import { Input } from "../ui/input";
import { Button } from "../ui/button";
import { cn } from "../../lib/utils";

export type DocumentSortType = "newest" | "oldest" | "name" | "status" | "size";
export type DocumentFilterType = "all" | "completed" | "processing" | "failed";

export interface DateRange {
  start: string;
  end: string;
}

interface DocumentFiltersProps {
  search: string;
  onSearchChange: (val: string) => void;
  sort: DocumentSortType;
  onSortChange: (val: DocumentSortType) => void;
  filter: DocumentFilterType;
  onFilterChange: (val: DocumentFilterType) => void;
  totalCount: number;
  filteredCount: number;

  // New Phase 5 advanced filters:
  selectedFolderId: string | null;
  onSelectedFolderChange: (val: string | null) => void;
  folders: { id: string; name: string }[];
  selectedLanguages: string[];
  onSelectedLanguagesChange: (langs: string[]) => void;
  availableLanguages: string[];
  dateRange: DateRange;
  onDateRangeChange: (range: DateRange) => void;
  onClearAll: () => void;

  // Saved Presets:
  savedPresets: Record<string, Record<string, unknown>>;
  onSavePreset: (name: string) => void;
  onDeletePreset: (name: string) => void;
  onLoadPreset: (presetName: string) => void;
}

export const DocumentFilters: React.FC<DocumentFiltersProps> = ({
  search,
  onSearchChange,
  sort,
  onSortChange,
  filter,
  onFilterChange,
  totalCount,
  filteredCount,
  selectedFolderId,
  onSelectedFolderChange,
  folders,
  selectedLanguages,
  onSelectedLanguagesChange,
  availableLanguages,
  dateRange,
  onDateRangeChange,
  onClearAll,
  savedPresets,
  onSavePreset,
  onDeletePreset,
  onLoadPreset,
}) => {
  const tabs: { label: string; value: DocumentFilterType }[] = [
    { label: "All Statuses", value: "all" },
    { label: "Completed", value: "completed" },
    { label: "Processing", value: "processing" },
    { label: "Failed", value: "failed" },
  ];

  const [presetInput, setPresetInput] = useState("");
  const [showPresetsMenu, setShowPresetsMenu] = useState(false);

  const toggleLanguage = (lang: string) => {
    if (selectedLanguages.includes(lang)) {
      onSelectedLanguagesChange(selectedLanguages.filter((l) => l !== lang));
    } else {
      onSelectedLanguagesChange([...selectedLanguages, lang]);
    }
  };

  const handleSavePreset = () => {
    const trimmed = presetInput.trim();
    if (!trimmed) return;
    onSavePreset(trimmed);
    setPresetInput("");
  };

  const isAnyFilterActive =
    !!search ||
    filter !== "all" ||
    selectedFolderId !== null ||
    selectedLanguages.length > 0 ||
    !!dateRange.start ||
    !!dateRange.end;

  return (
    <div className="space-y-4 bg-zinc-950 border border-zinc-900 rounded-2xl p-4.5">
      {/* Search and Sort row */}
      <div className="flex flex-col md:flex-row gap-3">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <Input
            placeholder="Search documents by name..."
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="pl-9 bg-zinc-900/60 border-zinc-900 focus-visible:ring-1 focus-visible:ring-violet-600 text-xs text-zinc-200 placeholder:text-zinc-500 rounded-lg h-9.5"
          />
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Saved Presets Button */}
          <div className="relative">
            <Button
              variant="outline"
              onClick={() => setShowPresetsMenu(!showPresetsMenu)}
              className="h-9.5 text-xs bg-zinc-900/60 border-zinc-900 hover:border-zinc-800 text-zinc-300 gap-1.5 cursor-pointer rounded-lg px-3.5"
            >
              <Filter size={13} />
              <span>Presets</span>
            </Button>
            {showPresetsMenu && (
              <div className="absolute right-0 top-11 z-30 w-64 bg-zinc-950 border border-zinc-850 rounded-xl p-3 shadow-xl space-y-3">
                <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider">
                  Filter Presets
                </div>
                {Object.keys(savedPresets).length === 0 ? (
                  <p className="text-[10px] text-zinc-500 italic">No saved presets.</p>
                ) : (
                  <div className="space-y-1.5 max-h-40 overflow-y-auto">
                    {Object.keys(savedPresets).map((name) => (
                      <div key={name} className="flex items-center justify-between gap-2 p-1.5 bg-zinc-900/40 rounded-lg">
                        <button
                          onClick={() => {
                            onLoadPreset(name);
                            setShowPresetsMenu(false);
                          }}
                          className="text-xs font-semibold text-zinc-300 hover:text-violet-400 text-left truncate flex-1 cursor-pointer"
                        >
                          {name}
                        </button>
                        <button
                          onClick={() => onDeletePreset(name)}
                          className="text-zinc-500 hover:text-red-400 cursor-pointer"
                        >
                          <Trash2 size={11} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                <div className="border-t border-zinc-900 pt-2 flex gap-1.5">
                  <Input
                    placeholder="New preset name..."
                    value={presetInput}
                    onChange={(e) => setPresetInput(e.target.value)}
                    className="h-8 bg-zinc-900 border-zinc-850 text-[10px] px-2"
                  />
                  <Button
                    onClick={handleSavePreset}
                    className="h-8 text-[10px] bg-violet-600 hover:bg-violet-750 text-white font-bold cursor-pointer"
                  >
                    <Save size={10} />
                  </Button>
                </div>
              </div>
            )}
          </div>

          {/* Sort Selector */}
          <select
            value={sort}
            onChange={(e) => onSortChange(e.target.value as DocumentSortType)}
            className="h-9.5 rounded-lg bg-zinc-900/60 border border-zinc-900 text-xs px-3 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-violet-600 text-zinc-300 font-semibold cursor-pointer"
          >
            <option value="newest">Sort: Newest</option>
            <option value="oldest">Sort: Oldest</option>
            <option value="name">Sort: A-Z</option>
            <option value="status">Sort: Status</option>
            <option value="size">Sort: Size</option>
          </select>
        </div>
      </div>

      {/* Advanced Filters Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 border-t border-zinc-900 pt-3.5">
        {/* Folder Selector (Combobox replacement) */}
        <div className="space-y-1.5">
          <label className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider flex items-center gap-1.5">
            <FolderOpen size={11} />
            <span>Folder</span>
          </label>
          <select
            value={selectedFolderId || ""}
            onChange={(e) => onSelectedFolderChange(e.target.value || null)}
            className="w-full h-8 rounded-lg bg-zinc-900/40 border border-zinc-900 text-[11px] px-2 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-violet-600 text-zinc-300 cursor-pointer"
          >
            <option value="">All Folders</option>
            {folders.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        </div>

        {/* Date Range Picker */}
        <div className="space-y-1.5 sm:col-span-2">
          <label className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider flex items-center gap-1.5">
            <Calendar size={11} />
            <span>Date Range</span>
          </label>
          <div className="flex items-center gap-2">
            <Input
              type="date"
              value={dateRange.start}
              onChange={(e) => onDateRangeChange({ ...dateRange, start: e.target.value })}
              className="h-8 bg-zinc-900/40 border-zinc-900 text-[10px] text-zinc-300"
            />
            <span className="text-zinc-650 text-xs">to</span>
            <Input
              type="date"
              value={dateRange.end}
              onChange={(e) => onDateRangeChange({ ...dateRange, end: e.target.value })}
              className="h-8 bg-zinc-900/40 border-zinc-900 text-[10px] text-zinc-300"
            />
          </div>
        </div>
      </div>

      {/* Language Chips & Active Status Tabs */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-t border-zinc-900 pt-3 pb-0.5">
        <div className="flex flex-col gap-1.5">
          <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-wider pl-0.5">
            Filter by Languages:
          </span>
          <div className="flex flex-wrap gap-1.5">
            {availableLanguages.length === 0 ? (
              <span className="text-[10px] text-zinc-600 italic">No language data</span>
            ) : (
              availableLanguages.map((lang) => {
                const isSelected = selectedLanguages.includes(lang);
                return (
                  <button
                    key={lang}
                    onClick={() => toggleLanguage(lang)}
                    className={cn(
                      "px-2.5 py-1 rounded-full text-[10px] font-bold transition-all duration-200 border cursor-pointer",
                      isSelected
                        ? "bg-violet-950/40 text-violet-400 border-violet-900/40 shadow-sm"
                        : "bg-zinc-900/30 text-zinc-500 border-transparent hover:text-zinc-400"
                    )}
                  >
                    {lang.toUpperCase()}
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Tab Status filters */}
        <div className="flex gap-1.5 self-end sm:self-auto">
          {tabs.map((tab) => (
            <button
              key={tab.value}
              onClick={() => onFilterChange(tab.value)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-200 border cursor-pointer",
                filter === tab.value
                  ? "bg-zinc-800 text-zinc-150 border-zinc-700/50"
                  : "text-zinc-500 hover:text-zinc-350 border-transparent"
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Filter Stats & Clear Action */}
      <div className="flex items-center justify-between text-[10px] text-zinc-500 font-medium pt-1 border-t border-zinc-900/40">
        <span className="font-mono font-bold">
          Showing {filteredCount} of {totalCount} files
        </span>

        {isAnyFilterActive && (
          <button
            onClick={onClearAll}
            className="flex items-center gap-1 text-violet-400 hover:text-violet-300 font-bold transition-colors duration-200 cursor-pointer"
          >
            <span>Clear All Filters</span>
            <X size={11} />
          </button>
        )}
      </div>
    </div>
  );
};
