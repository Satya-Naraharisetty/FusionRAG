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
      <Search
        size={14}
        className="absolute left-3 text-[var(--text-muted)] pointer-events-none group-focus-within:text-[var(--text-secondary)] transition-colors"
      />
      <Input
        id={id}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`pl-9 pr-10 bg-[var(--bg-input)] border border-[var(--border-default)] hover:border-[var(--border-hover)] text-xs rounded-[var(--radius-lg)] h-9 placeholder:text-[var(--text-muted)] focus:ring-2 focus:ring-[var(--accent-primary)]/20 focus:border-[var(--accent-primary)]/50 transition-all ${className}`}
      />
      {value && onClear ? (
        <button
          onClick={onClear}
          className="absolute right-3 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors cursor-pointer p-0.5 rounded-sm hover:bg-[var(--bg-tertiary)]"
          aria-label="Clear search"
        >
          <X size={13} />
        </button>
      ) : (
        <kbd className="pointer-events-none absolute right-3 hidden select-none items-center gap-0.5 rounded border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] px-1.5 font-mono text-[10px] font-medium text-[var(--text-muted)] sm:flex">
          ⌘K
        </kbd>
      )}
    </div>
  );
};
