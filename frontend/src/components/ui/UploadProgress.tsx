import React from "react";
import { cn } from "../../lib/utils";

interface UploadProgressProps {
  progress: number;
  status: "queued" | "uploading" | "processing" | "completed" | "error" | "paused";
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
  className?: string;
  animated?: boolean;
  /**
   * One-line caption rendered beneath the ring — e.g. the current pipeline
   * step ("Chunking…", "Indexing into vector DB — 3 of 12 chunks embedded").
   */
  footer?: React.ReactNode;
}

const SIZE_CONFIG = {
  sm: { ringSize: 16, barHeight: 3, strokeWidth: 2.5 },
  md: { ringSize: 24, barHeight: 4, strokeWidth: 3 },
  lg: { ringSize: 32, barHeight: 6, strokeWidth: 4 },
};

const STATUS_COLORS = {
  queued: "text-[var(--text-muted)]",
  uploading: "text-[var(--accent-primary)]",
  processing: "text-[var(--accent-primary)]",
  completed: "text-[var(--accent-success)]",
  error: "text-[var(--accent-error)]",
  paused: "text-[var(--accent-warning)]",
};

const STATUS_BG = {
  queued: "bg-[var(--text-muted)]",
  uploading: "bg-[var(--accent-primary)]",
  processing: "bg-[var(--accent-primary)]",
  completed: "bg-[var(--accent-success)]",
  error: "bg-[var(--accent-error)]",
  paused: "bg-[var(--accent-warning)]",
};

/** Shared footer caption rendered under the ring + label row. */
const Footer: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span className="text-[11px] leading-snug text-[var(--text-muted)]">{children}</span>
);

export const UploadProgress: React.FC<UploadProgressProps> = ({
  progress,
  status,
  size = "md",
  showLabel = true,
  className,
  animated = true,
  footer,
}) => {
  const config = SIZE_CONFIG[size];
  const radius = config.ringSize / 2 - config.strokeWidth;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - progress / 100);

  const ringStyle = {
    strokeDasharray: circumference,
    strokeDashoffset: offset,
    transition: animated ? "stroke-dashoffset 0.3s ease-out" : "none",
  };

  if (status === "completed" && progress === 100) {
    return (
      <div className={cn("flex flex-col gap-1", className)}>
        <div className="flex items-center gap-2">
          <span
            className={cn("flex-shrink-0", STATUS_COLORS[status])}
            style={{ width: config.ringSize, height: config.ringSize }}
          >
            <svg
              width={config.ringSize}
              height={config.ringSize}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </span>
          {showLabel && (
            <span className="text-xs font-mono font-bold" style={{ color: "var(--text-muted)" }}>
              Done
            </span>
          )}
        </div>
        {footer && <Footer>{footer}</Footer>}
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className={cn("flex flex-col gap-1", className)}>
        <div className="flex items-center gap-2">
          <span
            className={cn("flex-shrink-0", STATUS_COLORS[status])}
            style={{ width: config.ringSize, height: config.ringSize }}
          >
            <svg
              width={config.ringSize}
              height={config.ringSize}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
          </span>
          {showLabel && (
            <span className="text-xs font-mono font-bold" style={{ color: "var(--text-muted)" }}>
              Error
            </span>
          )}
        </div>
        {footer && <Footer>{footer}</Footer>}
      </div>
    );
  }

  // Background processing (chunking / vector DB): a sweeping arc spinner whose
  // progress value is derived from real server state, with the step caption
  // in the footer.
  if (status === "processing") {
    return (
      <div className={cn("flex flex-col gap-1", className)}>
        <div className="flex items-center gap-2">
          <span
            className="relative flex-shrink-0 animate-progress-spin"
            style={{ width: config.ringSize, height: config.ringSize }}
          >
            <svg
              width={config.ringSize}
              height={config.ringSize}
              viewBox="0 0 24 24"
              fill="none"
              className="transform -rotate-90"
            >
              <circle
                cx={config.ringSize / 2}
                cy={config.ringSize / 2}
                r={radius}
                fill="none"
                stroke="var(--border-color)"
                strokeWidth={config.strokeWidth}
              />
              <circle
                cx={config.ringSize / 2}
                cy={config.ringSize / 2}
                r={radius}
                fill="none"
                stroke={STATUS_BG.processing}
                strokeWidth={config.strokeWidth}
                strokeLinecap="round"
                strokeDasharray={`${0.28 * circumference} ${circumference}`}
              />
            </svg>
          </span>
          {showLabel && progress > 0 && (
            <span
              className="text-xs font-mono font-bold min-w-[28px] text-right"
              style={{ color: "var(--text-muted)" }}
            >
              {progress}%
            </span>
          )}
        </div>
        {footer && <Footer>{footer}</Footer>}
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <div className="flex items-center gap-2">
        <svg
          width={config.ringSize}
          height={config.ringSize}
          className={cn(
            "transform -rotate-90",
            animated ? "transition-transform duration-300" : "",
          )}
        >
          <circle
            cx={config.ringSize / 2}
            cy={config.ringSize / 2}
            r={radius}
            fill="none"
            stroke="var(--border-color)"
            strokeWidth={config.strokeWidth}
          />
          <circle
            cx={config.ringSize / 2}
            cy={config.ringSize / 2}
            r={radius}
            fill="none"
            stroke={STATUS_BG[status]}
            strokeWidth={config.strokeWidth}
            strokeLinecap="round"
            style={ringStyle}
            className={cn(animated ? "animate-progress" : "")}
          />
        </svg>
        {showLabel && (
          <span
            className="text-xs font-mono font-bold min-w-[28px] text-right"
            style={{ color: "var(--text-muted)" }}
          >
            {progress}%
          </span>
        )}
      </div>
      {footer && <Footer>{footer}</Footer>}
    </div>
  );
};

export default UploadProgress;
