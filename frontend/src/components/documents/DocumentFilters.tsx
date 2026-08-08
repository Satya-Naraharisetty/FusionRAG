import React, { useState } from "react";
import { Search, X, FolderOpen, Calendar, Filter, Save, Trash2 } from "lucide-react";
import { Button } from "../ui/Button";
import { cn } from "../../lib/utils";

export type DocumentSortType = "newest" | "oldest" | "name" | "status" | "size";
export type DocumentFilterType = "all" | "chat" | "completed" | "processing" | "failed";

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
  selectedFolderId: string | null;
  onSelectedFolderChange: (val: string | null) => void;
  folders: { id: string; name: string }[];
  selectedLanguages: string[];
  onSelectedLanguagesChange: (langs: string[]) => void;
  availableLanguages: string[];
  dateRange: DateRange;
  onDateRangeChange: (range: DateRange) => void;
  onClearAll: () => void;
  savedPresets: Record<string, Record<string, unknown>>;
  onSavePreset: (name: string) => void;
  onDeletePreset: (name: string) => void;
  onLoadPreset: (presetName: string) => void;
}

const STATUS_TABS: { label: string; value: DocumentFilterType }[] = [
  { label: "All",        value: "all" },
  { label: "Chat",       value: "chat" },
  { label: "Completed",  value: "completed" },
  { label: "Processing", value: "processing" },
  { label: "Failed",     value: "failed" },
];

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
  const [presetInput, setPresetInput]       = useState("");
  const [showPresetsMenu, setShowPresetsMenu] = useState(false);

  const toggleLanguage = (lang: string) => {
    onSelectedLanguagesChange(
      selectedLanguages.includes(lang)
        ? selectedLanguages.filter((l) => l !== lang)
        : [...selectedLanguages, lang]
    );
  };

  const isAnyFilterActive =
    !!search || filter !== "all" || selectedFolderId !== null ||
    selectedLanguages.length > 0 || !!dateRange.start || !!dateRange.end;

  return (
    <div className="space-y-3">
      {/* ── Row 1: search + sort + presets ── */}
      <div className="flex flex-col sm:flex-row gap-2">
        {/* Search */}
        <div className="relative flex-1">
          <Search
            size={13}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)] pointer-events-none"
          />
          <input
            type="text"
            placeholder="Search documents…"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full h-9 pl-8 pr-4 bg-[var(--bg-input)] border border-[var(--border-default)] hover:border-[var(--border-hover)] focus:border-[var(--accent-primary)]/50 focus:ring-2 focus:ring-[var(--accent-primary)]/20 rounded-[var(--radius-lg)] text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none transition-all"
          />
        </div>

        <div className="flex items-center gap-2">
          {/* Sort */}
          <select
            value={sort}
            onChange={(e) => onSortChange(e.target.value as DocumentSortType)}
            className="h-9 rounded-[var(--radius-lg)] bg-[var(--bg-input)] border border-[var(--border-default)] hover:border-[var(--border-hover)] text-xs px-3 text-[var(--text-primary)] cursor-pointer outline-none focus:border-[var(--accent-primary)]/50 transition-colors"
          >
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="name">A → Z</option>
            <option value="status">By status</option>
            <option value="size">By size</option>
          </select>

          {/* Presets */}
          <div className="relative">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowPresetsMenu(!showPresetsMenu)}
              className="h-9 gap-1.5"
            >
              <Filter size={12} />
              <span>Presets</span>
            </Button>

            {showPresetsMenu && (
              <div className="absolute right-0 top-11 z-30 w-60 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-[var(--radius-xl)] p-3 shadow-md space-y-2.5">
                <div className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                  Filter Presets
                </div>

                {Object.keys(savedPresets).length === 0 ? (
                  <p className="text-[11px] text-[var(--text-muted)] italic">No saved presets yet.</p>
                ) : (
                  <div className="space-y-1 max-h-36 overflow-y-auto">
                    {Object.keys(savedPresets).map((name) => (
                      <div
                        key={name}
                        className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-[var(--radius-md)] hover:bg-[var(--bg-tertiary)] transition-colors"
                      >
                        <button
                          onClick={() => { onLoadPreset(name); setShowPresetsMenu(false); }}
                          className="text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] text-left truncate flex-1 cursor-pointer transition-colors"
                        >
                          {name}
                        </button>
                        <button
                          onClick={() => onDeletePreset(name)}
                          className="text-[var(--text-muted)] hover:text-[var(--accent-error)] cursor-pointer transition-colors flex-shrink-0"
                          aria-label={`Delete preset ${name}`}
                        >
                          <Trash2 size={11} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                <div className="border-t border-[var(--border-subtle)] pt-2.5 flex gap-1.5">
                  <input
                    type="text"
                    placeholder="New preset name…"
                    value={presetInput}
                    onChange={(e) => setPresetInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && presetInput.trim() && onSavePreset(presetInput.trim())}
                    className="flex-1 h-8 bg-[var(--bg-input)] border border-[var(--border-default)] rounded-[var(--radius-md)] text-[11px] px-2 text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none focus:border-[var(--accent-primary)]/50 transition-colors"
                  />
                  <Button
                    size="sm"
                    className="h-8 px-2"
                    onClick={() => presetInput.trim() && onSavePreset(presetInput.trim())}
                    aria-label="Save preset"
                  >
                    <Save size={11} />
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Row 2: Advanced filters (folder + date range) ── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 border-t border-[var(--border-subtle)] pt-3">
        {/* Folder */}
        <div className="space-y-1.5">
          <label className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider flex items-center gap-1.5">
            <FolderOpen size={10} />
            Folder
          </label>
          <select
            value={selectedFolderId || ""}
            onChange={(e) => onSelectedFolderChange(e.target.value || null)}
            className="w-full h-8 rounded-[var(--radius-md)] bg-[var(--bg-input)] border border-[var(--border-default)] hover:border-[var(--border-hover)] text-[11px] px-2 text-[var(--text-primary)] cursor-pointer outline-none focus:border-[var(--accent-primary)]/50 transition-colors"
          >
            <option value="">All Folders</option>
            {folders.map((f) => (
              <option key={f.id} value={f.id}>{f.name}</option>
            ))}
          </select>
        </div>

        {/* Date range */}
        <div className="space-y-1.5 sm:col-span-2">
          <label className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider flex items-center gap-1.5">
            <Calendar size={10} />
            Date Range
          </label>
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={dateRange.start}
              onChange={(e) => onDateRangeChange({ ...dateRange, start: e.target.value })}
              className="flex-1 h-8 rounded-[var(--radius-md)] bg-[var(--bg-input)] border border-[var(--border-default)] text-[11px] px-2 text-[var(--text-primary)] outline-none focus:border-[var(--accent-primary)]/50 transition-colors cursor-pointer"
            />
            <span className="text-[var(--text-muted)] text-xs flex-shrink-0">to</span>
            <input
              type="date"
              value={dateRange.end}
              onChange={(e) => onDateRangeChange({ ...dateRange, end: e.target.value })}
              className="flex-1 h-8 rounded-[var(--radius-md)] bg-[var(--bg-input)] border border-[var(--border-default)] text-[11px] px-2 text-[var(--text-primary)] outline-none focus:border-[var(--accent-primary)]/50 transition-colors cursor-pointer"
            />
          </div>
        </div>
      </div>

      {/* ── Row 3: Language chips + status tabs + stats ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-t border-[var(--border-subtle)] pt-3">
        {/* Language chips */}
        <div className="flex flex-wrap gap-1.5 items-center">
          {availableLanguages.length > 0 && (
            <>
              <span className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider">Lang:</span>
              {availableLanguages.map((lang) => {
                const isSelected = selectedLanguages.includes(lang);
                return (
                  <button
                    key={lang}
                    onClick={() => toggleLanguage(lang)}
                    className={cn(
                      "px-2 py-0.5 rounded-[var(--radius-pill)] text-[10px] font-medium border transition-all duration-150 cursor-pointer",
                      isSelected
                        ? "bg-[var(--accent-primary)]/15 text-[var(--accent-primary)] border-[var(--accent-primary)]/30"
                        : "bg-transparent text-[var(--text-muted)] border-[var(--border-subtle)] hover:text-[var(--text-secondary)] hover:border-[var(--border-default)]"
                    )}
                  >
                    {lang.toUpperCase()}
                  </button>
                );
              })}
            </>
          )}
        </div>

        {/* Status tabs */}
        <div className="flex gap-1 self-end sm:self-auto flex-wrap">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => onFilterChange(tab.value)}
              className={cn(
                "px-2.5 py-1 rounded-[var(--radius-md)] text-[11px] font-medium transition-all duration-150 cursor-pointer",
                filter === tab.value
                  ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border-default)]"
                  : "text-[var(--text-muted)] hover:text-[var(--text-secondary)] border border-transparent"
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Stats + clear ── */}
      <div className="flex items-center justify-between text-[11px] text-[var(--text-muted)] border-t border-[var(--border-subtle)] pt-2">
        <span className="font-mono">
          {filteredCount} of {totalCount} documents
        </span>
        {isAnyFilterActive && (
          <button
            onClick={onClearAll}
            className="flex items-center gap-1 text-[var(--accent-primary)] hover:text-[var(--accent-secondary)] font-medium transition-colors cursor-pointer"
          >
            <span>Clear filters</span>
            <X size={11} />
          </button>
        )}
      </div>
    </div>
  );
};
