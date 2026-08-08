import { useCallback, useMemo } from "react";
import { ChatAttachment } from "../types";
import { UPLOAD_LIMITS } from "../lib/constants";
import toast from "react-hot-toast";

interface FileValidationOptions {
  maxSize?: number;
  acceptedTypes?: Record<string, string[]>;
  existingFiles?: ChatAttachment[];
  checkDuplicates?: boolean;
}

interface ValidationResult {
  isValid: boolean;
  error?: string;
  duplicateOf?: ChatAttachment;
}

export const useFileValidation = (options: FileValidationOptions = {}) => {
  const {
    maxSize = UPLOAD_LIMITS.CHAT_MAX_FILE_SIZE,
    acceptedTypes = UPLOAD_LIMITS.CHAT_ACCEPTED_TYPES,
    existingFiles = [],
    checkDuplicates = true,
  } = options;

  const acceptedExtensions = useMemo(() => {
    return Object.values(acceptedTypes).flat();
  }, [acceptedTypes]);

  const validateFile = useCallback(
    (file: File): ValidationResult => {
      // Check file size
      if (file.size > maxSize) {
        const maxMB = Math.round(maxSize / (1024 * 1024));
        return {
          isValid: false,
          error: `File "${file.name}" exceeds ${maxMB}MB limit.`,
        };
      }

      // Check file type
      const fileExt = file.name.split(".").pop()?.toLowerCase() || "";
      if (!acceptedExtensions.includes(fileExt)) {
        return {
          isValid: false,
          error: `File format ".${fileExt}" for "${file.name}" is not supported.`,
        };
      }

      // Check for duplicates
      if (checkDuplicates && existingFiles.length > 0) {
        const duplicate = existingFiles.find(
          (f) =>
            f.file.name === file.name &&
            f.file.size === file.size &&
            f.file.lastModified === file.lastModified
        );
        if (duplicate) {
          return {
            isValid: false,
            error: `File "${file.name}" is already attached.`,
            duplicateOf: duplicate,
          };
        }
      }

      return { isValid: true };
    },
    [maxSize, acceptedExtensions, existingFiles, checkDuplicates]
  );

  const validateFiles = useCallback(
    (files: File[]): { valid: File[]; invalid: Array<{ file: File; error: string }> } => {
      const valid: File[] = [];
      const invalid: Array<{ file: File; error: string }> = [];

      files.forEach((file) => {
        const result = validateFile(file);
        if (result.isValid) {
          valid.push(file);
        } else {
          invalid.push({ file, error: result.error || "Unknown error" });
          if (result.error) {
            toast.error(result.error);
          }
        }
      });

      return { valid, invalid };
    },
    [validateFile]
  );

  return { validateFile, validateFiles };
};

export default useFileValidation;