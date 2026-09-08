import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const cardVariants = cva(
  "rounded-[var(--radius-xl)] text-[var(--text-primary)] transition-all duration-200",
  {
    variants: {
      variant: {
        default: "border border-[var(--border-subtle)] bg-[var(--bg-secondary)]",
        subtle: "border border-[var(--border-subtle)] bg-[var(--bg-secondary)]",
        open: "border-0 bg-transparent shadow-none",
        glass: "border border-[var(--border-subtle)] bg-[var(--bg-secondary)]/80 backdrop-blur-md",
        glassStrong:
          "border border-[var(--border-default)] bg-[var(--bg-tertiary)]/90 backdrop-blur-md",
        outlined: "border border-[var(--border-default)] bg-transparent",
        elevated:
          "border border-[var(--border-subtle)] bg-[var(--bg-elevated)] shadow-xs rounded-[var(--radius-2xl)]",
      },
      elevation: {
        none: "shadow-none",
        low: "shadow-xs",
        medium: "shadow-sm",
        high: "shadow-md",
        glow: "shadow-xs",
      },
      interactive: {
        true: "transition-all duration-200 hover:border-[var(--border-hover)] hover:bg-[var(--bg-tertiary)] cursor-pointer",
        false: "",
      },
      padding: {
        none: "",
        sm: "p-3.5",
        default: "p-5",
        lg: "p-6",
      },
    },
    compoundVariants: [],
    defaultVariants: {
      variant: "default",
      elevation: "none",
      interactive: false,
      padding: "default",
    },
  },
);

export interface CardProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof cardVariants> {
  ref?: React.Ref<HTMLDivElement>;
}

const Card = ({
  className,
  variant,
  elevation,
  interactive,
  padding,
  children,
  ref,
  ...props
}: CardProps) => (
  <div
    ref={ref}
    className={cn(cardVariants({ variant, elevation, interactive, padding, className }))}
    {...props}
  >
    {children}
  </div>
);
Card.displayName = "Card";

const CardHeader = ({ className, ref, ...props }: React.HTMLAttributes<HTMLDivElement> & { ref?: React.Ref<HTMLDivElement> }) => (
  <div ref={ref} className={cn("flex flex-col space-y-1.5", className)} {...props} />
);
CardHeader.displayName = "CardHeader";

const CardTitle = ({ className, ref, ...props }: React.HTMLAttributes<HTMLHeadingElement> & { ref?: React.Ref<HTMLHeadingElement> }) => (
  <h3
    ref={ref}
    className={cn("text-xl font-semibold leading-tight tracking-tight", className)}
    {...props}
  />
);
CardTitle.displayName = "CardTitle";

const CardDescription = ({ className, ref, ...props }: React.HTMLAttributes<HTMLParagraphElement> & { ref?: React.Ref<HTMLParagraphElement> }) => (
  <p ref={ref} className={cn("text-sm text-muted-foreground", className)} {...props} />
);
CardDescription.displayName = "CardDescription";

const CardContent = ({ className, ref, ...props }: React.HTMLAttributes<HTMLDivElement> & { ref?: React.Ref<HTMLDivElement> }) => (
  <div ref={ref} className={cn("pt-0", className)} {...props} />
);
CardContent.displayName = "CardContent";

const CardFooter = ({ className, ref, ...props }: React.HTMLAttributes<HTMLDivElement> & { ref?: React.Ref<HTMLDivElement> }) => (
  <div
    ref={ref}
    className={cn("flex items-center pt-4 border-t border-[var(--border-subtle)]", className)}
    {...props}
  />
);
CardFooter.displayName = "CardFooter";

export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent, cardVariants };
