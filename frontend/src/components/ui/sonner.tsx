import { Toaster as Sonner } from "sonner"

type ToasterProps = React.ComponentProps<typeof Sonner>

const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      theme="light"
      className="toaster group"
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-canvas-elevated group-[.toaster]:text-ink group-[.toaster]:border-hairline-strong group-[.toaster]:shadow-2xl group-[.toaster]:rounded-md font-sans text-xs",
          description: "group-[.toast]:text-body font-sans text-xs",
          actionButton:
            "group-[.toast]:bg-primary group-[.toast]:text-white font-medium text-xs",
          cancelButton:
            "group-[.toast]:bg-canvas-soft group-[.toast]:text-body",
          success: "group-[.toast]:border-live-pulse/30 group-[.toast]:text-live-pulse",
          error: "group-[.toast]:border-state-failed/30 group-[.toast]:text-state-failed",
          info: "group-[.toast]:border-telemetry-cyan/30 group-[.toast]:text-telemetry-cyan-soft",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
