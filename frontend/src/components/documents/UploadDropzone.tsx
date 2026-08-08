import React, { useCallback, useState, useMemo } from "react";
import { useDropzone } from "react-dropzone";
import {
  Upload,
  X,
  AlertCircle,
  Play,
  Pause,
  ArrowUp,
  GripVertical,
  CheckCircle2,
} from "lucide-react";
import { useUploadDocument } from "../../hooks/useDocuments";
import { UPLOAD_LIMITS } from "../../lib/constants";
import { Button } from "../ui/Button";
import { FileTypeBadge } from "../ui/FileTypeBadge";
import { UploadProgress } from "../ui/UploadProgress";
import toast from "react-hot-toast";

interface QueueFile {
  id: string;
  file: File;
  status: "queued" | "uploading" | "paused" | "completed" | "error";
  progress: number;
  controller?: AbortController;
}

export const UploadDropzone: React.FC = () => {
  const uploadMutation = useUploadDocument();
  const [queue, setQueue]           = useState<QueueFile[]>([]);
  const [draggedIdx, setDraggedIdx] = useState<number | null>(null);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const newItems: QueueFile[] = [];
    acceptedFiles.forEach((file) => {
      if (file.size > UPLOAD_LIMITS.MAX_FILE_SIZE) {
        toast.error(`"${file.name}" exceeds the 50 MB size limit.`);
        return;
      }
      const ext = file.name.split(".").pop()?.toLowerCase() || "";
      if (!["pdf", "txt", "docx", "doc", "md"].includes(ext)) {
        toast.error(`".${ext}" is not a supported format.`);
        return;
      }
      newItems.push({
        id: `upload-${Math.random().toString(36).substring(2, 9)}`,
        file,
        status: "queued",
        progress: 0,
      });
    });
    if (newItems.length > 0) {
      setQueue((prev) => [...prev, ...newItems]);
      toast.success(`Added ${newItems.length} file${newItems.length > 1 ? "s" : ""} to queue.`);
    }
  }, []);

  const startUpload = async (item: QueueFile) => {
    if (item.status === "uploading" || item.status === "completed") return;
    const controller = new AbortController();
    setQueue((prev) =>
      prev.map((q) => (q.id === item.id ? { ...q, status: "uploading", controller } : q))
    );
    try {
      await uploadMutation.mutateAsync({
        file: item.file,
        onProgress: (progressEvent: unknown) => {
          const pe = progressEvent as { loaded: number; total?: number };
          const progress = pe.total ? Math.round((pe.loaded * 100) / pe.total) : 0;
          setQueue((prev) =>
            prev.map((q) => (q.id === item.id ? { ...q, progress } : q))
          );
        },
        signal: controller.signal,
      });
      setQueue((prev) =>
        prev.map((q) => (q.id === item.id ? { ...q, status: "completed", progress: 100 } : q))
      );
      toast.success(`Uploaded "${item.file.name}"`);
    } catch (err: unknown) {
      const isAborted =
        (err as Error)?.name === "CanceledError" || (err as Error)?.name === "AbortError";
      if (!isAborted) {
        setQueue((prev) =>
          prev.map((q) => (q.id === item.id ? { ...q, status: "error" } : q))
        );
        toast.error(`Failed to upload "${item.file.name}".`);
      }
    }
  };

  const handlePause = (id: string) => {
    const item = queue.find((q) => q.id === id);
    if (item?.status === "uploading" && item.controller) {
      item.controller.abort();
      setQueue((prev) =>
        prev.map((q) => (q.id === id ? { ...q, status: "paused", controller: undefined } : q))
      );
    }
  };

  const handleResume = (id: string) => {
    const item = queue.find((q) => q.id === id);
    if (item?.status === "paused") startUpload(item);
  };

  const handleCancel = (id: string) => {
    const item = queue.find((q) => q.id === id);
    if (item) {
      item.controller?.abort();
      setQueue((prev) => prev.filter((q) => q.id !== id));
    }
  };

  const uploadAll = () => {
    const pending = queue.filter(
      (q) => q.status === "queued" || q.status === "paused" || q.status === "error"
    );
    if (pending.length === 0) { toast.error("No pending files to upload."); return; }
    pending.forEach((item) => startUpload(item));
  };

  const batchSummary = useMemo(() => {
    if (queue.length === 0) return { completed: 0, total: 0, overallProgress: 0 };
    const completed = queue.filter((q) => q.status === "completed").length;
    const totalProgress = queue.reduce((sum, q) => sum + q.progress, 0);
    return { completed, total: queue.length, overallProgress: Math.round(totalProgress / queue.length) };
  }, [queue]);

  const handleDragStart = (idx: number) => setDraggedIdx(idx);

  const handleDragOver = (e: React.DragEvent, targetIdx: number) => {
    e.preventDefault();
    if (draggedIdx === null || draggedIdx === targetIdx) return;
    const updated = [...queue];
    const item = updated.splice(draggedIdx, 1)[0];
    updated.splice(targetIdx, 0, item);
    setQueue(updated);
    setDraggedIdx(targetIdx);
  };

  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop,
    maxSize: UPLOAD_LIMITS.MAX_FILE_SIZE,
    accept: UPLOAD_LIMITS.ACCEPTED_TYPES,
  });

  return (
    <div className="space-y-3">
      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={`group rounded-[var(--radius-2xl)] p-8 flex flex-col items-center justify-center text-center cursor-pointer transition-all duration-200 ${
          isDragActive
            ? "border-2 border-dashed border-[var(--accent-primary)]/70 bg-[var(--accent-primary)]/8"
            : "border border-dashed border-[var(--border-default)] bg-transparent hover:border-[var(--border-hover)] hover:bg-[var(--bg-secondary)]"
        }`}
      >
        <input {...getInputProps()} />
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] text-[var(--text-muted)] mb-3 group-hover:text-[var(--text-secondary)] transition-colors">
          <Upload size={16} />
        </div>
        <p className="text-sm font-medium text-[var(--text-primary)] mb-1">
          {isDragActive ? "Drop files here…" : "Drag & drop files here"}
        </p>
        <p className="text-xs text-[var(--text-muted)]">
          PDF, TXT, DOCX, MD · max 50 MB
        </p>
      </div>

      {/* File rejections */}
      {fileRejections.length > 0 && (
        <div className="flex items-center gap-2 rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-3 text-xs font-medium text-[var(--text-secondary)]">
          <AlertCircle size={14} className="flex-shrink-0 text-[var(--accent-error)]" />
          <span>Some files were rejected (too large or unsupported format).</span>
        </div>
      )}

      {/* Upload queue */}
      {queue.length > 0 && (
        <div className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-2xl)] p-4 space-y-3">
          {/* Queue header */}
          <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-3">
            <div>
              <div className="flex items-center gap-2">
                <h4 className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                  Upload Queue ({queue.length})
                </h4>
                {batchSummary.completed === batchSummary.total && (
                  <span className="flex items-center gap-1 text-[11px] font-medium text-[var(--accent-success)]">
                    <CheckCircle2 size={11} /> All done
                  </span>
                )}
              </div>
              <p className="text-[11px] text-[var(--text-muted)] font-mono mt-0.5">
                {batchSummary.completed}/{batchSummary.total} completed · {batchSummary.overallProgress}%
              </p>
            </div>
            {queue.some((q) => ["queued", "paused", "error"].includes(q.status)) && (
              <Button size="sm" onClick={uploadAll} className="gap-1.5 text-xs">
                <ArrowUp size={12} />
                Upload All
              </Button>
            )}
          </div>

          {/* Batch progress bar */}
          <div className="w-full bg-[var(--bg-tertiary)] rounded-full h-1 overflow-hidden">
            <div
              className="h-1 rounded-full bg-gradient-to-r from-[var(--accent-primary)] to-[var(--accent-success)] transition-all duration-300"
              style={{ width: `${batchSummary.overallProgress}%` }}
            />
          </div>

          {/* File rows */}
          <div className="space-y-1.5 pt-1">
            {queue.map((item, idx) => (
              <div
                key={item.id}
                draggable="true"
                onDragStart={() => handleDragStart(idx)}
                onDragOver={(e) => handleDragOver(e, idx)}
                onDragEnd={() => setDraggedIdx(null)}
                className="flex items-center justify-between gap-3 p-3 bg-[var(--bg-tertiary)]/40 hover:bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] rounded-[var(--radius-lg)] transition-colors duration-150"
              >
                <div className="flex items-center gap-2.5 min-w-0 flex-1">
                  <div
                    className="cursor-grab active:cursor-grabbing text-[var(--text-muted)] hover:text-[var(--text-secondary)] flex-shrink-0"
                    title="Reorder"
                  >
                    <GripVertical size={13} />
                  </div>

                  <FileTypeBadge filename={item.file.name} variant="card" className="w-8 h-8 flex-shrink-0" />

                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-medium text-[var(--text-primary)] truncate">
                        {item.file.name}
                      </p>
                      <FileTypeBadge filename={item.file.name} variant="minimal" size="sm" className="flex-shrink-0" />
                    </div>
                    <UploadProgress progress={item.progress} status={item.status} size="sm" showLabel />
                  </div>
                </div>

                <div className="flex items-center gap-0.5 flex-shrink-0">
                  {item.status === "uploading" && (
                    <Button
                      variant="ghost"
                      size="iconSm"
                      onClick={() => handlePause(item.id)}
                      className="h-7 w-7"
                      title="Pause"
                      aria-label="Pause upload"
                    >
                      <Pause size={11} />
                    </Button>
                  )}
                  {item.status === "paused" && (
                    <Button
                      variant="ghost"
                      size="iconSm"
                      onClick={() => handleResume(item.id)}
                      className="h-7 w-7"
                      title="Resume"
                      aria-label="Resume upload"
                    >
                      <Play size={11} className="fill-current" />
                    </Button>
                  )}
                  {item.status !== "completed" && (
                    <Button
                      variant="ghost"
                      size="iconSm"
                      onClick={() => handleCancel(item.id)}
                      className="h-7 w-7 hover:text-[var(--accent-error)]"
                      title="Cancel"
                      aria-label="Cancel upload"
                    >
                      <X size={11} />
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default UploadDropzone;
