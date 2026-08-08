import React from "react";
import { Search, X } from "lucide-react";
import { Input } from "./Input";

interface SearchBoxProps {
  placeholder?: string;
  value: string;
  onChange: (value: string) => void;
  onClear?: () => void;
  id?: string;
  className?: string;
}

export const SearchBox: React.FC<SearchBoxProps> = ({
  placeholder = "Search...",
  value,
  onChange,
  onClear,
  id,
  className,
}) => {
  return (
    <div className="relative flex items-center w-full group">
      <Search size={13} className="absolute left-3.5 text-zinc-550 pointer-events-none group-focus-within:text-zinc-300 transition-colors" />
      <Input
        id={id}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`pl-9.5 pr-14 bg-zinc-900/15 hover:bg-zinc-900/30 border-[var(--border-color)] hover:border-[var(--border-hover)] text-xs rounded-xl h-9 placeholder:text-zinc-500 focus:ring-1 focus:ring-zinc-700 focus:border-zinc-700 transition-all ${className}`}
      />
      {value && onClear ? (
        <button
          onClick={onClear}
          className="absolute right-3 text-zinc-550 hover:text-zinc-300 transition-colors cursor-pointer"
          aria-label="Clear search"
        >
          <X size={13} />
        </button>
      ) : (
        <kbd className="pointer-events-none absolute right-3 hidden select-none items-center gap-0.5 rounded border border-zinc-800 bg-zinc-900 px-1.5 font-mono text-[9px] font-bold text-zinc-550 opacity-80 sm:flex">
          Ctrl+/
        </kbd>
      )}
    </div>
  );
};
