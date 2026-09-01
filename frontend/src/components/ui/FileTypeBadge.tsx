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

const FILE_TYPE_CONFIG: Record<string, { label: string; icon: React.ReactNode }> = {
  pdf: { label: "PDF", icon: <FileText size={10} /> },
  md: { label: "MD", icon: <FileText size={10} /> },
  docx: { label: "DOCX", icon: <FileText size={10} /> },
  doc: { label: "DOC", icon: <FileText size={10} /> },
  txt: { label: "TXT", icon: <FileText size={10} /> },
  png: { label: "PNG", icon: <Image size={10} /> },
  jpg: { label: "JPG", icon: <Image size={10} /> },
  jpeg: { label: "JPEG", icon: <Image size={10} /> },
  webp: { label: "WEBP", icon: <Image size={10} /> },
  gif: { label: "GIF", icon: <Image size={10} /> },
  js: { label: "JS", icon: <FileCode size={10} /> },
  ts: { label: "TS", icon: <FileCode size={10} /> },
  tsx: { label: "TSX", icon: <FileCode size={10} /> },
  jsx: { label: "JSX", icon: <FileCode size={10} /> },
  py: { label: "PY", icon: <FileCode size={10} /> },
  json: { label: "JSON", icon: <FileCode size={10} /> },
  yaml: { label: "YAML", icon: <FileCode size={10} /> },
  yml: { label: "YML", icon: <FileCode size={10} /> },
};

const SIZE_CLASSES = {
  sm: "px-1.5 py-0.5 text-[9px] gap-1",
  md: "px-2 py-0.5 text-[10px] gap-1.5",
  lg: "px-2.5 py-1 text-[11px] gap-2",
};

const VARIANT_CLASSES = {
  default:
    "inline-flex items-center font-bold uppercase tracking-wider rounded-full border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] text-[var(--text-secondary)]",
  minimal:
    "inline-flex items-center font-medium rounded-full border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] text-[var(--text-secondary)]",
  card: "flex items-center justify-center font-bold uppercase tracking-wider rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] text-[var(--text-secondary)] shadow-xs",
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
    icon: <FileText size={10} />,
  };

  if (variant === "card") {
    return (
      <div
        className={cn(
          "flex flex-col items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] text-[var(--text-secondary)] shadow-xs flex-shrink-0",
          className,
        )}
      >
        <div className="mb-0.5">{config.icon}</div>
        <span className="text-[9px]">{config.label}</span>
      </div>
    );
  }

  return (
    <span className={cn(SIZE_CLASSES[size], VARIANT_CLASSES[variant], className)}>
      <span className="flex-shrink-0">{config.icon}</span>
      <span>{config.label}</span>
    </span>
  );
};

export default FileTypeBadge;
