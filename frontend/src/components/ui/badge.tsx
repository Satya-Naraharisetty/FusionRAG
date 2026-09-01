import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-[var(--radius-pill)] border px-2 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/40",
  {
    variants: {
      variant: {
        default: "border-transparent bg-[var(--accent-primary)]/15 text-[var(--accent-primary)]",
        secondary:
          "border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] text-[var(--text-secondary)]",
        destructive: "border-transparent bg-red-500/10 text-red-400",
        outline: "border border-[var(--border-default)] text-[var(--text-primary)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
