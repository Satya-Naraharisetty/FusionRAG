import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const cardVariants = cva(
  "rounded-lg border bg-card text-card-foreground",
  {
    variants: {
      variant: {
        default: "border-zinc-800 bg-zinc-950/50",
        glass: "border-glass-border bg-glass-bg/50 backdrop-blur-md",
        glassStrong: "border-glass-border-strong bg-glass-bg-strong/50 backdrop-blur-lg",
        outlined: "border-2 border-zinc-800 bg-transparent",
        elevated: "border-zinc-800/50 bg-zinc-950 shadow-elevation-2",
      },
      elevation: {
        none: "shadow-none",
        low: "shadow-elevation-1",
        medium: "shadow-elevation-2",
        high: "shadow-elevation-3",
        glow: "shadow-elevation-glow",
      },
      interactive: {
        true: "transition-all duration-300 ease-standard hover:shadow-elevation-3 hover:-translate-y-0.5 hover:border-zinc-700 cursor-pointer",
        false: "",
      },
      padding: {
        none: "",
        sm: "p-4",
        default: "p-6",
        lg: "p-8",
      },
    },
    compoundVariants: [
      {
        variant: "glass",
        interactive: true,
        className: "hover:bg-glass-bg/70 hover:border-glass-border-strong",
      },
      {
        variant: "default",
        interactive: true,
        className: "hover:bg-zinc-950/70",
      },
    ],
    defaultVariants: {
      variant: "default",
      elevation: "low",
      interactive: false,
      padding: "default",
    },
  }
)

const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof cardVariants>
>(({ className, variant, elevation, interactive, padding, children, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(cardVariants({ variant, elevation, interactive, padding, className }))}
    {...props}
  >
    {children}
  </div>
))
Card.displayName = "Card"

const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex flex-col space-y-1.5", className)}
    {...props}
  />
))
CardHeader.displayName = "CardHeader"

const CardTitle = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <h3
    ref={ref}
    className={cn("text-xl font-semibold leading-tight tracking-tight", className)}
    {...props}
  />
))
CardTitle.displayName = "CardTitle"

const CardDescription = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props}
  />
))
CardDescription.displayName = "CardDescription"

const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("pt-0", className)} {...props} />
))
CardContent.displayName = "CardContent"

const CardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex items-center pt-4 border-t border-zinc-800/50", className)}
    {...props}
  />
))
CardFooter.displayName = "CardFooter"

export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent, cardVariants }