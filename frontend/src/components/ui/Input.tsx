import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  labelClassName?: string;
  error?: string;
  helperText?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  ref?: React.Ref<HTMLInputElement>;
}

const Input = ({
  className,
  type,
  label,
  labelClassName,
  error,
  helperText,
  leftIcon,
  rightIcon,
  id,
  disabled,
  required,
  "aria-describedby": ariaDescribedBy,
  ref,
  ...props
}: InputProps) => {
  const fallbackId = React.useId();
  const inputId = id || fallbackId;
  const errorId = error ? `${inputId}-error` : undefined;
  const helperId = helperText ? `${inputId}-helper` : undefined;
  const describedBy = [errorId, helperId, ariaDescribedBy].filter(Boolean).join(" ") || undefined;
  const invalidProps = error ? { "aria-invalid": "true" as const } : {};

  return (
    <div className="w-full">
      {label && (
        <label
          htmlFor={inputId}
          className={cn("mb-1.5 block text-xs font-medium text-(--text-secondary)", labelClassName)}
        >
          {label}
          {required && (
            <span className="ml-1 text-(--accent-error)" aria-hidden="true">
              *
            </span>
          )}
        </label>
      )}
      <div className="relative">
        {leftIcon && (
          <div
            className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-(--text-muted)"
            aria-hidden="true"
          >
            {leftIcon}
          </div>
        )}
        <input
          type={type}
          id={inputId}
          disabled={disabled}
          required={required}
          aria-describedby={describedBy}
          {...invalidProps}
          className={cn(
            "flex h-10 w-full rounded-xl border border-(--border-default) bg-(--bg-input) pl-3.5 pr-3.5 text-sm text-(--text-primary) placeholder:text-(--text-muted) transition-all duration-200 hover:border-(--border-hover) focus:border-(--accent-primary)/50 focus:outline-none focus:ring-2 focus:ring-(--accent-primary)/20 disabled:cursor-not-allowed disabled:opacity-40",
            leftIcon && "pl-10",
            rightIcon && "pr-10",
            error &&
              "border-(--accent-error)/50 focus:border-(--accent-error) focus:ring-(--accent-error)/20",
            className,
          )}
          ref={ref}
          {...props}
        />
        {rightIcon && (
          <div className="absolute inset-y-0 right-0 flex items-center pr-3 text-(--text-muted) z-10">
            {rightIcon}
          </div>
        )}
        {error && (
          <p
            id={errorId}
            className="mt-1.5 flex items-center gap-1 text-sm text-(--accent-error)"
            role="alert"
          >
            <svg
              className="h-3.5 w-3.5 shrink-0"
              fill="currentColor"
              viewBox="0 0 20 20"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
            {error}
          </p>
        )}
        {helperText && !error && (
          <p id={helperId} className="mt-1.5 text-sm text-(--text-muted)">
            {helperText}
          </p>
        )}
      </div>
    </div>
  );
};
Input.displayName = "Input";

export { Input };
