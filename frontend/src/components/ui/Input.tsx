import * as React from "react"
import { cn } from "@/lib/utils"

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  labelClassName?: string
  error?: string
  helperText?: string
  leftIcon?: React.ReactNode
  rightIcon?: React.ReactNode
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, label, labelClassName, error, helperText, leftIcon, rightIcon, id, disabled, required, "aria-describedby": ariaDescribedBy, ...props }, ref) => {
    const fallbackId = React.useId()
    const inputId = id || fallbackId
    const errorId = error ? `${inputId}-error` : undefined
    const helperId = helperText ? `${inputId}-helper` : undefined
    const describedBy = [errorId, helperId, ariaDescribedBy].filter(Boolean).join(" ") || undefined

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={inputId}
            className={cn("block text-xs font-medium text-[var(--text-secondary)] mb-1.5", labelClassName)}
          >
            {label}
            {required && <span className="text-[var(--accent-error)] ml-1" aria-hidden="true">*</span>}
          </label>
        )}
        <div className="relative">
          {leftIcon && (
            <div
              className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none text-[var(--text-muted)]"
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
            aria-invalid={error ? "true" : "false"}
            aria-describedby={describedBy}
            className={cn(
              "flex h-10 w-full rounded-[var(--radius-xl)] border border-[var(--border-default)] bg-[var(--bg-input)] text-[var(--text-primary)] text-sm placeholder:text-[var(--text-muted)] transition-all duration-200 focus:outline-none focus:border-[var(--accent-primary)]/50 focus:ring-2 focus:ring-[var(--accent-primary)]/20 hover:border-[var(--border-hover)] disabled:cursor-not-allowed disabled:opacity-40",
              leftIcon && "pl-10",
              rightIcon && "pr-10",
              error && "border-[var(--accent-error)]/50 focus:border-[var(--accent-error)] focus:ring-[var(--accent-error)]/20",
              className
            )}
            ref={ref}
            {...props}
          />
          {rightIcon && (
            <div
              className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none text-[var(--text-muted)]"
              aria-hidden="true"
            >
              {rightIcon}
            </div>
          )}
          {error && (
            <p id={errorId} className="mt-1.5 text-sm text-[var(--accent-error)] flex items-center gap-1" role="alert">
              <svg className="h-3.5 w-3.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              {error}
            </p>
          )}
          {helperText && !error && (
            <p id={helperId} className="mt-1.5 text-sm text-[var(--text-muted)]">
              {helperText}
            </p>
          )}
        </div>
      </div>
    )
  }
)
Input.displayName = "Input"

export { Input }