import * as React from "react";
import { cn } from "@/lib/utils";
import { Button } from "./Button";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  variant?: "default" | "inline" | "fullscreen";
  className?: string;
}

export const EmptyState = React.forwardRef<HTMLDivElement, EmptyStateProps>(
  (
    {
      icon,
      title,
      description,
      action,
      actionLabel,
      onAction,
      variant = "default",
      className,
      ...props
    },
    ref,
  ) => {
    const handleAction = () => {
      if (action) return;
      onAction?.();
    };

    return (
      <div
        ref={ref}
        className={cn(
          "flex flex-col items-center justify-center text-center",
          variant === "default" && "py-12 px-6",
          variant === "inline" && "py-8 px-4",
          variant === "fullscreen" && "min-h-[400px] px-6",
          className,
        )}
        {...props}
      >
        {icon && (
          <div
            className={cn(
              "mb-3 flex items-center justify-center text-[var(--text-muted)]",
              variant === "fullscreen" && "text-5xl mb-4",
              variant !== "fullscreen" && "text-3xl",
            )}
            aria-hidden="true"
          >
            {icon}
          </div>
        )}
        <h3
          className={cn(
            "font-semibold text-[var(--text-primary)]",
            variant === "fullscreen" && "text-lg",
            variant !== "fullscreen" && "text-sm",
          )}
        >
          {title}
        </h3>
        {description && (
          <p
            className={cn(
              "mt-1.5 text-[var(--text-secondary)] max-w-sm text-xs leading-relaxed",
              variant === "fullscreen" && "text-sm mt-2",
            )}
          >
            {description}
          </p>
        )}
        {(action || (actionLabel && onAction)) && (
          <div className="mt-5">
            {action || (
              <Button onClick={handleAction} variant="secondary" size="sm" className="gap-2">
                {actionLabel}
              </Button>
            )}
          </div>
        )}
      </div>
    );
  },
);
EmptyState.displayName = "EmptyState";

interface LoadingStateProps {
  size?: "sm" | "md" | "lg" | "xl";
  label?: string;
  variant?: "spinner" | "dots" | "pulse" | "skeleton";
  className?: string;
}

export const LoadingState = React.forwardRef<HTMLDivElement, LoadingStateProps>(
  ({ size = "md", label, variant = "spinner", className, ...props }, ref) => {
    const sizeClasses = {
      sm: "h-4 w-4",
      md: "h-6 w-6",
      lg: "h-8 w-8",
      xl: "h-10 w-10",
    };

    const labelClasses = {
      sm: "text-xs mt-1.5",
      md: "text-xs mt-2",
      lg: "text-sm mt-2.5",
      xl: "text-sm mt-3",
    };

    if (variant === "skeleton") {
      return (
        <div ref={ref} className={cn("space-y-2.5", className)} {...props}>
          <div
            className={cn(
              "h-4 bg-[var(--bg-tertiary)] rounded-[var(--radius-md)] animate-pulse",
              size === "lg" && "h-5",
              size === "xl" && "h-6",
            )}
          />
          <div
            className={cn(
              "h-4 bg-[var(--bg-tertiary)] rounded-[var(--radius-md)] animate-pulse w-3/4",
              size === "lg" && "h-5",
              size === "xl" && "h-6",
            )}
          />
          <div
            className={cn(
              "h-4 bg-[var(--bg-tertiary)] rounded-[var(--radius-md)] animate-pulse w-1/2",
              size === "lg" && "h-5",
              size === "xl" && "h-6",
            )}
          />
        </div>
      );
    }

    if (variant === "dots") {
      return (
        <div ref={ref} className={cn("flex flex-col items-center gap-2", className)} {...props}>
          <div className="flex gap-1.5" aria-hidden="true">
            <span
              className={cn(
                "h-2 w-2 rounded-full bg-[var(--accent-primary)] animate-bounce",
                sizeClasses[size],
              )}
              style={{ animationDelay: "0ms" }}
            />
            <span
              className={cn(
                "h-2 w-2 rounded-full bg-[var(--accent-primary)] animate-bounce",
                sizeClasses[size],
              )}
              style={{ animationDelay: "150ms" }}
            />
            <span
              className={cn(
                "h-2 w-2 rounded-full bg-[var(--accent-primary)] animate-bounce",
                sizeClasses[size],
              )}
              style={{ animationDelay: "300ms" }}
            />
          </div>
          {label && (
            <span className={cn("text-[var(--text-muted)] font-medium", labelClasses[size])}>
              {label}
            </span>
          )}
        </div>
      );
    }

    if (variant === "pulse") {
      return (
        <div ref={ref} className={cn("flex flex-col items-center gap-2", className)} {...props}>
          <div
            className={cn(
              "rounded-full bg-[var(--accent-primary)]/20 animate-pulse",
              sizeClasses[size],
            )}
            aria-hidden="true"
          />
          {label && (
            <span className={cn("text-[var(--text-muted)] font-medium", labelClasses[size])}>
              {label}
            </span>
          )}
        </div>
      );
    }

    return (
      <div ref={ref} className={cn("flex flex-col items-center gap-2", className)} {...props}>
        <svg
          className={cn("animate-spin text-[var(--text-muted)]", sizeClasses[size])}
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="3"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
        {label && (
          <span className={cn("text-[var(--text-muted)] font-medium", labelClasses[size])}>
            {label}
          </span>
        )}
      </div>
    );
  },
);
LoadingState.displayName = "LoadingState";

interface ErrorStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  variant?: "default" | "inline" | "toast";
  className?: string;
}

export const ErrorState = React.forwardRef<HTMLDivElement, ErrorStateProps>(
  (
    {
      icon,
      title,
      description,
      action,
      actionLabel,
      onAction,
      variant = "default",
      className,
      ...props
    },
    ref,
  ) => {
    const handleAction = () => {
      if (action) return;
      onAction?.();
    };

    return (
      <div
        ref={ref}
        className={cn(
          "flex flex-col items-center justify-center text-center gap-2.5",
          variant === "default" && "py-12 px-6",
          variant === "inline" && "py-6 px-4",
          variant === "toast" &&
            "flex-row items-start gap-3 p-4 rounded-[var(--radius-xl)] border border-red-500/20 bg-red-500/10 text-left",
          className,
        )}
        role="alert"
        {...props}
      >
        <div
          className={cn(
            "flex items-center justify-center text-red-400",
            variant === "toast" && "flex-shrink-0 mt-0.5",
            variant !== "toast" && "text-2xl p-2.5 rounded-full bg-red-500/10",
          )}
          aria-hidden="true"
        >
          {icon || (
            <svg
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          )}
        </div>
        <div className={cn(variant === "toast" && "flex-1")}>
          <h3
            className={cn(
              "font-medium text-[var(--text-primary)]",
              variant === "toast" && "text-xs",
              variant !== "toast" && "text-sm font-semibold",
            )}
          >
            {title}
          </h3>
          {description && (
            <p
              className={cn(
                "text-[var(--text-secondary)] max-w-sm text-xs mt-1 leading-relaxed",
                variant === "toast" && "text-xs mt-0.5",
              )}
            >
              {description}
            </p>
          )}
          {(action || (actionLabel && onAction)) && (
            <div
              className={cn(
                "mt-4 flex gap-2 justify-center",
                variant === "toast" && "mt-2 justify-start",
              )}
            >
              {action || (
                <Button onClick={handleAction} variant="destructive" size="xs">
                  {actionLabel || "Retry"}
                </Button>
              )}
            </div>
          )}
        </div>
      </div>
    );
  },
);
ErrorState.displayName = "ErrorState";

export { LoadingState as Loader };
