import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-full font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-canvas disabled:pointer-events-none disabled:opacity-50 select-none text-[13px] active:scale-[0.98] transition-transform duration-100",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-white hover:bg-primary-hover shadow-sm",
        destructive:
          "bg-state-failed text-white hover:bg-red-600 shadow-sm",
        outline:
          "border border-hairline-strong bg-white hover:bg-canvas-elevated hover:text-ink text-ink",
        secondary:
          "bg-canvas-elevated text-ink hover:bg-canvas-soft border border-hairline",
        ghost:
          "text-body hover:bg-canvas-elevated hover:text-ink",
        cyan:
          "bg-telemetry-cyan/10 text-telemetry-cyan-soft border border-telemetry-cyan/25 hover:bg-telemetry-cyan/20",
        emerald:
          "bg-live-pulse/10 text-live-pulse border border-live-pulse/25 hover:bg-live-pulse/20",
        link:
          "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-5 py-2",
        sm: "h-8 rounded-full px-3 text-xs",
        lg: "h-control-lg rounded-full px-6 text-sm",
        icon: "h-control w-control",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
