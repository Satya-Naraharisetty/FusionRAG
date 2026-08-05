import React, { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, X, AlertCircle, FileText } from "lucide-react";
import { useUploadDocument } from "../../hooks/useDocuments";
import { UPLOAD_LIMITS } from "../../lib/constants";
import { Button } from "../ui/button";

interface ActiveUpload {
  id: string;
  filename: string;
  progress: number;
  controller: AbortController;
}

export const UploadDropzone: React.FC = () => {
  const uploadMutation = useUploadDocument();
  const [activeUploads, setActiveUploads] = useState<ActiveUpload[]>([]);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      for (const file of acceptedFiles) {
        if (file.size > UPLOAD_LIMITS.MAX_FILE_SIZE) {
          continue;
        }

        const id = Math.random().toString();
        const controller = new AbortController();

        const newUpload: ActiveUpload = {
          id,
          filename: file.name,
          progress: 0,
          controller,
        };

        setActiveUploads((prev) => [newUpload, ...prev]);

        try {
          await uploadMutation.mutateAsync({
            file,
            onProgress: (progressEvent: unknown) => {
              const pe = progressEvent as { loaded: number; total?: number };
              const progress = pe.total
                ? Math.round((pe.loaded * 100) / pe.total)
                : 0;
              setActiveUploads((prev) =>
                prev.map((up) => (up.id === id ? { ...up, progress } : up))
              );
            },
            signal: controller.signal,
          });
        } catch (_e) {
          // Failure handled in mutation
        } finally {
          setActiveUploads((prev) => prev.filter((up) => up.id !== id));
        }
      }
    },
    [uploadMutation]
  );

  const handleCancel = (id: string) => {
    const upload = activeUploads.find((up) => up.id === id);
    if (upload) {
      upload.controller.abort();
      setActiveUploads((prev) => prev.filter((up) => up.id !== id));
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
        className={`border-2 border-dashed rounded-2xl p-8 flex flex-col items-center justify-center text-center cursor-pointer transition-all duration-200 ${
          isDragActive
            ? "border-violet-500 bg-violet-950/10"
            : "border-zinc-800 bg-zinc-950/20 hover:border-zinc-700 hover:bg-zinc-900/10"
        }`}
      >
        <input {...getInputProps()} />
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-zinc-900 border border-zinc-800 text-zinc-400 mb-3">
          <Upload size={18} />
        </div>
        <p className="text-xs font-semibold text-zinc-200 mb-1">
          {isDragActive ? "Drop files here..." : "Drag & drop files here"}
        </p>
        <p className="text-[10px] text-zinc-500">
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

      {/* Active Uploading List */}
      {activeUploads.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider pl-1">
            Uploading ({activeUploads.length})
          </h4>
          <div className="space-y-2">
            {activeUploads.map((up) => (
              <div
                key={up.id}
                className="flex items-center justify-between gap-3 p-3 bg-zinc-950/40 border border-zinc-900 rounded-xl"
              >
                <div className="flex items-center gap-2.5 min-w-0 flex-1">
                  <FileText size={16} className="text-violet-400 flex-shrink-0" />
                  <div className="min-w-0 flex-1 space-y-1">
                    <p className="text-xs font-semibold text-zinc-300 truncate">
                      {up.filename}
                    </p>
                    <div className="flex items-center gap-2">
                      {/* Progress bar container */}
                      <div className="w-full bg-zinc-900 rounded-full h-1">
                        <div
                          className="bg-violet-600 h-1 rounded-full transition-all duration-200"
                          style={{ width: `${up.progress}%` }}
                        />
                      </div>
                      <span className="text-[10px] font-mono font-bold text-zinc-400 min-w-[28px]">
                        {up.progress}%
                      </span>
                    </div>
                  </div>
                </div>

                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => handleCancel(up.id)}
                  className="h-8 w-8 hover:bg-zinc-900 text-zinc-500 hover:text-zinc-300 cursor-pointer"
                  aria-label="Cancel upload"
                >
                  <X size={14} />
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
