import React from "react";
import { cn } from "../../lib/utils";

interface UploadProgressProps {
  progress: number;
  status: "queued" | "uploading" | "completed" | "error" | "paused";
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
  className?: string;
  animated?: boolean;
}

const SIZE_CONFIG = {
  sm: { ringSize: 16, barHeight: 3, strokeWidth: 2.5 },
  md: { ringSize: 24, barHeight: 4, strokeWidth: 3 },
  lg: { ringSize: 32, barHeight: 6, strokeWidth: 4 },
};

const STATUS_COLORS = {
  queued: "text-[var(--text-muted)]",
  uploading: "text-[var(--accent-primary)]",
  completed: "text-[var(--accent-success)]",
  error: "text-[var(--accent-error)]",
  paused: "text-[var(--accent-warning)]",
};

const STATUS_BG = {
  queued: "bg-[var(--text-muted)]",
  uploading: "bg-[var(--accent-primary)]",
  completed: "bg-[var(--accent-success)]",
  error: "bg-[var(--accent-error)]",
  paused: "bg-[var(--accent-warning)]",
};

export const UploadProgress: React.FC<UploadProgressProps> = ({
  progress,
  status,
  size = "md",
  showLabel = true,
  className,
  animated = true,
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
      <div className={cn("flex items-center gap-2", className)}>
        <span
          className={cn("flex-shrink-0", STATUS_COLORS[status])}
          style={{ width: config.ringSize, height: config.ringSize }}
        >
          <svg width={config.ringSize} height={config.ringSize} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </span>
        {showLabel && <span className="text-xs font-mono font-bold" style={{ color: "var(--text-muted)" }}>Done</span>}
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className={cn("flex items-center gap-2", className)}>
        <span
          className={cn("flex-shrink-0", STATUS_COLORS[status])}
          style={{ width: config.ringSize, height: config.ringSize }}
        >
          <svg width={config.ringSize} height={config.ringSize} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
        </span>
        {showLabel && <span className="text-xs font-mono font-bold" style={{ color: "var(--text-muted)" }}>Error</span>}
      </div>
    );
  }

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <svg
        width={config.ringSize}
        height={config.ringSize}
        className={cn("transform -rotate-90", animated ? "transition-transform duration-300" : "")}
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
        <span className="text-xs font-mono font-bold min-w-[28px] text-right" style={{ color: "var(--text-muted)" }}>
          {progress}%
        </span>
      )}
    </div>
  );
};

export default UploadProgress;