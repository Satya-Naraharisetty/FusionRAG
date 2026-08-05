import React from "react";
import { Search } from "lucide-react";
import { Input } from "../ui/input";

export type DocumentSortType = "newest" | "oldest" | "name" | "status";
export type DocumentFilterType = "all" | "completed" | "processing" | "failed";

interface DocumentFiltersProps {
  search: string;
  onSearchChange: (val: string) => void;
  sort: DocumentSortType;
  onSortChange: (val: DocumentSortType) => void;
  filter: DocumentFilterType;
  onFilterChange: (val: DocumentFilterType) => void;
  totalCount: number;
  filteredCount: number;
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
}) => {
  const tabs: { label: string; value: DocumentFilterType }[] = [
    { label: "All", value: "all" },
    { label: "Completed", value: "completed" },
    { label: "Processing", value: "processing" },
    { label: "Failed", value: "failed" },
  ];

  return (
    <div className="space-y-4">
      {/* Search and Sort row */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <Input
            placeholder="Search documents by name..."
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="pl-9 bg-zinc-900 border-zinc-800 focus-visible:ring-1 focus-visible:ring-violet-600 text-xs text-zinc-200 placeholder:text-zinc-500"
          />
        </div>
        
        <select
          value={sort}
          onChange={(e) => onSortChange(e.target.value as DocumentSortType)}
          className="h-9 rounded-md bg-zinc-900 border border-zinc-800 text-xs px-3 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-violet-600 text-zinc-300 font-semibold cursor-pointer"
        >
          <option value="newest">Sort: Newest</option>
          <option value="oldest">Sort: Oldest</option>
          <option value="name">Sort: A-Z</option>
          <option value="status">Sort: Status</option>
        </select>
      </div>

      {/* Tabs and Counts row */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-900 pb-2">
        <div className="flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.value}
              onClick={() => onFilterChange(tab.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-200 ${
                filter === tab.value
                  ? "bg-zinc-800 text-zinc-150 border border-zinc-700/50"
                  : "text-zinc-500 hover:text-zinc-300 border border-transparent"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <span className="text-[10px] text-zinc-500 font-mono font-bold">
          Showing {filteredCount} of {totalCount} files
        </span>
      </div>
    </div>
  );
};
