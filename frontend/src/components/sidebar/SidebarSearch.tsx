import React, { useEffect, useState } from "react";
import { Search, X } from "lucide-react";
import { Input } from "../ui/input";

interface SidebarSearchProps {
  onSearch: (query: string) => void;
}

export const SidebarSearch: React.FC<SidebarSearchProps> = ({ onSearch }) => {
  const [value, setValue] = useState(() => {
    return sessionStorage.getItem("sidebar-search") || "";
  });

  useEffect(() => {
    onSearch(value);
    sessionStorage.setItem("sidebar-search", value);
  }, [value, onSearch]);

  return (
    <div className="relative w-full px-3 py-2">
      <div className="relative flex items-center">
        <Search size={16} className="absolute left-3 text-zinc-500" />
        <Input
          placeholder="Search conversations... (Ctrl+/)"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="h-9 w-full bg-zinc-900 border-zinc-800 text-zinc-200 pl-9 pr-8 focus-visible:ring-1 focus-visible:ring-violet-600 rounded-md text-xs placeholder:text-zinc-500"
          id="sidebar-search-input"
        />
        {value && (
          <button
            onClick={() => setValue("")}
            className="absolute right-3 text-zinc-500 hover:text-zinc-300"
            aria-label="Clear search"
          >
            <X size={14} />
          </button>
        )}
      </div>
    </div>
  );
};
