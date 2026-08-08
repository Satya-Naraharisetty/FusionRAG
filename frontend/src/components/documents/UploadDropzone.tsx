import React, { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import {
  Upload,
  X,
  AlertCircle,
  FileText,
  Play,
  Pause,
  ArrowUp,
  GripVertical,
} from "lucide-react";
import { useUploadDocument } from "../../hooks/useDocuments";
import { UPLOAD_LIMITS } from "../../lib/constants";
import { Button } from "../ui/Button";
import toast from "react-hot-toast";
import { cn } from "../../lib/utils";

interface QueueFile {
  id: string;
  file: File;
  status: "queued" | "uploading" | "paused" | "completed" | "error";
  progress: number;
  controller?: AbortController;
}

export const UploadDropzone: React.FC = () => {
  const uploadMutation = useUploadDocument();
  const [queue, setQueue] = useState<QueueFile[]>([]);

  // Drag and drop sorting in queue
  const [draggedIdx, setDraggedIdx] = useState<number | null>(null);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const newItems: QueueFile[] = [];

    acceptedFiles.forEach((file) => {
      // Validate file size
      if (file.size > UPLOAD_LIMITS.MAX_FILE_SIZE) {
        toast.error(`File "${file.name}" exceeds the 50MB size limit.`);
        return;
      }

      // Validate file type
      const fileExt = file.name.split(".").pop()?.toLowerCase() || "";
      const validExts = ["pdf", "txt", "docx", "doc", "md"];
      if (!validExts.includes(fileExt)) {
        toast.error(`File format ".${fileExt}" for "${file.name}" is not supported.`);
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
      toast.success(`Added ${newItems.length} file(s) to the queue.`);
    }
  }, []);

  const startUpload = async (item: QueueFile) => {
    if (item.status === "uploading" || item.status === "completed") return;

    const controller = new AbortController();
    setQueue((prev) =>
      prev.map((q) =>
        q.id === item.id ? { ...q, status: "uploading", controller } : q
      )
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
      toast.success(`Successfully uploaded "${item.file.name}"!`);
    } catch (err: unknown) {
      const isAborted = (err as Error)?.name === "CanceledError" || (err as Error)?.name === "AbortError";
      if (isAborted) {
        // Paused/cancelled states handled separately
      } else {
        setQueue((prev) =>
          prev.map((q) => (q.id === item.id ? { ...q, status: "error" } : q))
        );
        toast.error(`Failed to upload "${item.file.name}".`);
      }
    }
  };

  const handlePause = (id: string) => {
    const item = queue.find((q) => q.id === id);
    if (item && item.status === "uploading" && item.controller) {
      item.controller.abort();
      setQueue((prev) =>
        prev.map((q) => (q.id === id ? { ...q, status: "paused", controller: undefined } : q))
      );
      toast.custom(
        (t) => (
          <div className={`${t.visible ? 'animate-enter' : 'animate-leave'} max-w-md w-full bg-zinc-900 border border-zinc-800 shadow-lg rounded-xl pointer-events-auto flex p-3 text-xs text-zinc-400 font-semibold gap-2`}>
            <Pause size={14} className="text-amber-500 flex-shrink-0" />
            <span>Paused upload for "{item.file.name}".</span>
          </div>
        )
      );
    }
  };

  const handleResume = (id: string) => {
    const item = queue.find((q) => q.id === id);
    if (item && item.status === "paused") {
      startUpload(item);
    }
  };

  const handleCancel = (id: string) => {
    const item = queue.find((q) => q.id === id);
    if (item) {
      if (item.controller) {
        item.controller.abort();
      }
      setQueue((prev) => prev.filter((q) => q.id !== id));
      toast.error(`Cancelled upload for "${item.file.name}".`);
    }
  };

  const uploadAll = () => {
    const pending = queue.filter((q) => q.status === "queued" || q.status === "paused" || q.status === "error");
    if (pending.length === 0) {
      toast.error("No pending files to upload.");
      return;
    }
    pending.forEach((item) => startUpload(item));
  };

  // Reorder queue logic
  const handleDragStart = (idx: number) => {
    setDraggedIdx(idx);
  };

  const handleDragOver = (e: React.DragEvent, targetIdx: number) => {
    e.preventDefault();
    if (draggedIdx === null || draggedIdx === targetIdx) return;

    const updatedQueue = [...queue];
    const item = updatedQueue.splice(draggedIdx, 1)[0];
    updatedQueue.splice(targetIdx, 0, item);
    setQueue(updatedQueue);
    setDraggedIdx(targetIdx);
  };

  const handleDragEnd = () => {
    setDraggedIdx(null);
  };

  const getFileIcon = (filename: string) => {
    const ext = filename.split(".").pop()?.toLowerCase();
    switch (ext) {
      case "pdf":
        return <FileText size={16} className="text-red-400 flex-shrink-0" />;
      case "md":
        return <FileText size={16} className="text-fuchsia-400 flex-shrink-0" />;
      case "docx":
      case "doc":
        return <FileText size={16} className="text-blue-400 flex-shrink-0" />;
      default:
        return <FileText size={16} className="text-zinc-400 flex-shrink-0" />;
    }
  };

  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop,
    maxSize: UPLOAD_LIMITS.MAX_FILE_SIZE,
    accept: UPLOAD_LIMITS.ACCEPTED_TYPES,
  });

  return (
    <div className="space-y-4">
      {/* Drag Drop Area */}
      <div
        {...getRootProps()}
        className={`group border border-dashed rounded-2xl p-8.5 flex flex-col items-center justify-center text-center cursor-pointer transition-all duration-200 ${
          isDragActive
            ? "border-primary/60 bg-primary/5 shadow-xs"
            : "border-[var(--border-color)] bg-zinc-900/5 hover:border-[var(--border-hover)] hover:bg-zinc-900/10 hover:shadow-xs"
        }`}
      >
        <input {...getInputProps()} />
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-zinc-900/60 border border-zinc-800 text-zinc-400 mb-3 group-hover:text-zinc-200 group-hover:border-zinc-700 transition-all duration-300">
          <Upload size={16} />
        </div>
        <p className="text-xs font-semibold text-zinc-200 mb-1">
          {isDragActive ? "Drop files here..." : "Drag & drop files here"}
        </p>
        <p className="text-[10px] text-zinc-500 leading-normal">
          Supports PDF, TXT, DOCX, MD (max 50MB)
        </p>
      </div>

      {/* File Size Error Display */}
      {fileRejections.length > 0 && (
        <div className="flex items-center gap-2 p-3 bg-red-950/10 border border-red-900/20 rounded-xl text-red-400 text-[10px] font-medium leading-normal">
          <AlertCircle size={14} className="flex-shrink-0" />
          <span>Some files were rejected because they exceed 50MB or are unsupported.</span>
        </div>
      )}

      {/* Uploading Queue Display */}
      {queue.length > 0 && (
        <div className="space-y-3 bg-zinc-950/40 border border-zinc-900 rounded-2xl p-4">
          <div className="flex items-center justify-between">
            <h4 className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider pl-1 select-none">
              Upload Queue ({queue.length})
            </h4>
            {queue.some((q) => q.status === "queued" || q.status === "paused") && (
              <Button
                onClick={uploadAll}
                className="h-7 text-[10px] font-bold bg-violet-600 hover:bg-violet-750 text-white px-3 gap-1 cursor-pointer"
              >
                <ArrowUp size={11} />
                <span>Upload All</span>
              </Button>
            )}
          </div>

          <div className="space-y-2">
            {queue.map((item, idx) => (
              <div
                key={item.id}
                draggable="true"
                onDragStart={() => handleDragStart(idx)}
                onDragOver={(e) => handleDragOver(e, idx)}
                onDragEnd={handleDragEnd}
                className="flex items-center justify-between gap-3 p-3 bg-zinc-900/20 hover:bg-zinc-900/40 border border-zinc-900 rounded-xl transition-all duration-300"
              >
                <div className="flex items-center gap-2.5 min-w-0 flex-1">
                  <div className="cursor-grab active:cursor-grabbing text-zinc-600 hover:text-zinc-400" title="Reorder file">
                    <GripVertical size={13} />
                  </div>
                  {getFileIcon(item.file.name)}
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-semibold text-zinc-300 truncate">
                        {item.file.name}
                      </p>
                      <span
                        className={cn(
                          "text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded",
                          item.status === "queued" && "bg-zinc-800 text-zinc-500",
                          item.status === "uploading" && "bg-blue-950/40 text-blue-400 animate-pulse",
                          item.status === "paused" && "bg-amber-950/40 text-amber-500",
                          item.status === "completed" && "bg-emerald-950/40 text-emerald-400",
                          item.status === "error" && "bg-red-950/40 text-red-500"
                        )}
                      >
                        {item.status}
                      </span>
                    </div>

                    {item.status === "uploading" && (
                      <div className="flex items-center gap-2">
                        <div className="w-full bg-zinc-950 rounded-full h-1">
                          <div
                            className="bg-violet-600 h-1 rounded-full transition-all duration-200"
                            style={{ width: `${item.progress}%` }}
                          />
                        </div>
                        <span className="text-[9px] font-mono font-bold text-zinc-400 min-w-[28px]">
                          {item.progress}%
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-1 flex-shrink-0">
                  {item.status === "uploading" && (
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handlePause(item.id)}
                      className="h-8 w-8 hover:bg-zinc-900 text-zinc-500 hover:text-zinc-300 cursor-pointer"
                      title="Pause"
                    >
                      <Pause size={12} />
                    </Button>
                  )}
                  {item.status === "paused" && (
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleResume(item.id)}
                      className="h-8 w-8 hover:bg-zinc-900 text-zinc-500 hover:text-zinc-300 cursor-pointer"
                      title="Resume"
                    >
                      <Play size={12} className="fill-current" />
                    </Button>
                  )}
                  {item.status !== "completed" && (
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleCancel(item.id)}
                      className="h-8 w-8 hover:bg-zinc-900 text-zinc-500 hover:text-zinc-300 cursor-pointer"
                      title="Cancel"
                    >
                      <X size={12} />
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
