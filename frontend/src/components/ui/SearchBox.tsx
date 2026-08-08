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
    <div className="relative flex items-center w-full">
      <Search size={14} className="absolute left-3 text-zinc-500 pointer-events-none" />
      <Input
        id={id}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`pl-9 pr-8 bg-zinc-900/20 border-zinc-850 hover:border-zinc-800 text-xs rounded-lg placeholder:text-zinc-500 focus-visible:ring-1 focus-visible:ring-zinc-700 focus-visible:border-zinc-700 transition-all ${className}`}
      />
      {value && onClear && (
        <button
          onClick={onClear}
          className="absolute right-3 text-zinc-500 hover:text-zinc-350 transition-colors cursor-pointer"
          aria-label="Clear search"
        >
          <X size={13} />
        </button>
      )}
    </div>
  );
};
