import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-1 focus:ring-primary",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-white",
        secondary:
          "border-hairline bg-canvas-elevated text-ink",
        destructive:
          "border-state-failed/30 bg-state-failed/10 text-state-failed",
        outline:
          "border-hairline text-ink",
        live:
          "border-live-pulse/30 bg-live-pulse/10 text-live-pulse",
        ringing:
          "border-state-ringing/30 bg-state-ringing/10 text-state-ringing",
        cyan:
          "border-telemetry-cyan/30 bg-telemetry-cyan/10 text-telemetry-cyan-soft",
        amber:
          "border-telemetry-amber/30 bg-telemetry-amber/10 text-telemetry-amber",
        mono:
          "font-mono text-[11px] tracking-wide uppercase border-hairline bg-canvas-elevated text-body",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
