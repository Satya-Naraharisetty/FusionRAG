import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-md)] text-sm font-medium transition-all duration-200 ease-standard focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/50 focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--bg-primary)] disabled:pointer-events-none disabled:opacity-40 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 cursor-pointer select-none",
  {
    variants: {
      variant: {
        default:
          "bg-[var(--accent-primary)] text-white hover:opacity-90 active:scale-[0.98] shadow-xs",
        destructive:
          "bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 hover:border-red-500/30 active:scale-[0.98]",
        outline:
          "border border-[var(--border-default)] bg-transparent text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:border-[var(--border-hover)] active:bg-[var(--bg-elevated)]",
        secondary:
          "bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border-subtle)] hover:bg-[var(--bg-elevated)] hover:border-[var(--border-default)] active:scale-[0.98]",
        ghost:
          "bg-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] active:bg-[var(--bg-elevated)]",
        link: "text-[var(--accent-primary)] underline-offset-4 hover:underline",
        success:
          "bg-emerald-600/90 text-white hover:bg-emerald-600 active:scale-[0.98] shadow-xs",
      },
      size: {
        xs: "h-7 px-2.5 text-xs rounded-[var(--radius-sm)] gap-1.5",
        sm: "h-8 px-3 text-xs font-medium rounded-[var(--radius-md)]",
        default: "h-10 px-4 text-sm font-medium rounded-[var(--radius-lg)]",
        lg: "h-11 px-5 text-sm font-medium rounded-[var(--radius-xl)]",
        xl: "h-12 px-6 text-base font-medium rounded-[var(--radius-xl)]",
        icon: "h-9 w-9 rounded-[var(--radius-md)]",
        iconSm: "h-8 w-8 rounded-[var(--radius-sm)]",
        iconLg: "h-10 w-10 rounded-[var(--radius-lg)]",
      },
      loading: {
        true: "opacity-70 cursor-wait [&_svg]:animate-spin",
        false: "",
      },
    },
    compoundVariants: [],
    defaultVariants: {
      variant: "default",
      size: "default",
      loading: false,
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
  loading?: boolean
  leftIcon?: React.ReactNode
  rightIcon?: React.ReactNode
  fullWidth?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, leftIcon, rightIcon, fullWidth, asChild = false, children, disabled, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    const isDisabled = disabled || loading

    return (
      <Comp
        className={cn(buttonVariants({ variant, size, loading, className }), fullWidth && "w-full")}
        ref={ref}
        disabled={isDisabled}
        aria-busy={loading}
        aria-disabled={isDisabled}
        {...props}
      >
        {loading ? (
          <svg
            className="h-4 w-4 animate-spin"
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
        ) : leftIcon ? (
          <span className="flex-shrink-0" aria-hidden="true">{leftIcon}</span>
        ) : null}
        {children}
        {!loading && rightIcon && <span className="flex-shrink-0" aria-hidden="true">{rightIcon}</span>}
      </Comp>
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }