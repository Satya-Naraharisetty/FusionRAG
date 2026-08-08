import React from "react";
import { FileText, Image, FileCode } from "lucide-react";
import { cn } from "../../lib/utils";

interface FileTypeBadgeProps {
  filename: string;
  contentType?: string;
  size?: "sm" | "md" | "lg";
  variant?: "default" | "minimal" | "card";
  className?: string;
}

const FILE_TYPE_CONFIG: Record<string, { label: string; bg: string; border: string; text: string; icon: React.ReactNode }> = {
  pdf: { label: "PDF", bg: "bg-red-500/10", border: "border-red-500/30", text: "text-red-500", icon: <FileText size={10} /> },
  md: { label: "MD", bg: "bg-fuchsia-500/10", border: "border-fuchsia-500/30", text: "text-fuchsia-500", icon: <FileText size={10} /> },
  docx: { label: "DOCX", bg: "bg-blue-500/10", border: "border-blue-500/30", text: "text-blue-500", icon: <FileText size={10} /> },
  doc: { label: "DOC", bg: "bg-blue-500/10", border: "border-blue-500/30", text: "text-blue-500", icon: <FileText size={10} /> },
  txt: { label: "TXT", bg: "bg-zinc-500/10", border: "border-zinc-500/30", text: "text-zinc-500", icon: <FileText size={10} /> },
  png: { label: "PNG", bg: "bg-emerald-500/10", border: "border-emerald-500/30", text: "text-emerald-500", icon: <Image size={10} /> },
  jpg: { label: "JPG", bg: "bg-emerald-500/10", border: "border-emerald-500/30", text: "text-emerald-500", icon: <Image size={10} /> },
  jpeg: { label: "JPEG", bg: "bg-emerald-500/10", border: "border-emerald-500/30", text: "text-emerald-500", icon: <Image size={10} /> },
  webp: { label: "WEBP", bg: "bg-emerald-500/10", border: "border-emerald-500/30", text: "text-emerald-500", icon: <Image size={10} /> },
  gif: { label: "GIF", bg: "bg-emerald-500/10", border: "border-emerald-500/30", text: "text-emerald-500", icon: <Image size={10} /> },
  js: { label: "JS", bg: "bg-yellow-500/10", border: "border-yellow-500/30", text: "text-yellow-500", icon: <FileCode size={10} /> },
  ts: { label: "TS", bg: "bg-blue-500/10", border: "border-blue-500/30", text: "text-blue-500", icon: <FileCode size={10} /> },
  tsx: { label: "TSX", bg: "bg-blue-500/10", border: "border-blue-500/30", text: "text-blue-500", icon: <FileCode size={10} /> },
  jsx: { label: "JSX", bg: "bg-yellow-500/10", border: "border-yellow-500/30", text: "text-yellow-500", icon: <FileCode size={10} /> },
  py: { label: "PY", bg: "bg-green-500/10", border: "border-green-500/30", text: "text-green-500", icon: <FileCode size={10} /> },
  json: { label: "JSON", bg: "bg-amber-500/10", border: "border-amber-500/30", text: "text-amber-500", icon: <FileCode size={10} /> },
  yaml: { label: "YAML", bg: "bg-amber-500/10", border: "border-amber-500/30", text: "text-amber-500", icon: <FileCode size={10} /> },
  yml: { label: "YML", bg: "bg-amber-500/10", border: "border-amber-500/30", text: "text-amber-500", icon: <FileCode size={10} /> },
};

const SIZE_CLASSES = {
  sm: "px-1.5 py-0.5 text-[9px] gap-1",
  md: "px-2 py-0.5 text-[10px] gap-1.5",
  lg: "px-2.5 py-1 text-[11px] gap-2",
};

const VARIANT_CLASSES = {
  default: "inline-flex items-center font-bold uppercase tracking-wider rounded-full border",
  minimal: "inline-flex items-center font-medium rounded-full border",
  card: "flex items-center justify-center font-bold uppercase tracking-wider rounded-xl border shadow-xs",
};

export const FileTypeBadge: React.FC<FileTypeBadgeProps> = ({
  filename,
  contentType,
  size = "md",
  variant = "default",
  className,
}) => {
  const ext = filename.split(".").pop()?.toLowerCase() || "";
  const mimeType = contentType?.split("/")[1]?.toLowerCase() || "";
  const key = ext || mimeType;
  const config = FILE_TYPE_CONFIG[key] || {
    label: ext.toUpperCase() || "FILE",
    bg: "bg-zinc-500/10",
    border: "border-zinc-500/30",
    text: "text-zinc-500",
    icon: <FileText size={10} />,
  };

  if (variant === "card") {
    return (
      <div
        className={cn(
          "flex flex-col items-center justify-center rounded-xl border shadow-xs flex-shrink-0",
          config.bg,
          config.border,
          config.text,
          className
        )}
      >
        <div className="mb-0.5">{config.icon}</div>
        <span className="text-[9px]">{config.label}</span>
      </div>
    );
  }

  return (
    <span
      className={cn(
        SIZE_CLASSES[size],
        VARIANT_CLASSES[variant],
        config.bg,
        config.border,
        config.text,
        className
      )}
    >
      <span className="flex-shrink-0">{config.icon}</span>
      <span>{config.label}</span>
    </span>
  );
};

export default FileTypeBadge;