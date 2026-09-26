"use client"

import * as React from "react"
import * as RechartsPrimitive from "recharts"
import { cn } from "cn"

// Format: { THEME: { LABEL: CODE } }
type ChartConfig = {
  [k in string]: {
    label?: React.ReactNode
    icon?: React.ComponentType
  } & (
    | { color?: string; theme?: never }
    | { color?: never; theme: Record<"light" | "dark", string> }
  )
}

type ChartContextProps = {
  config: ChartConfig
}

const ChartContext = React.createContext<ChartContextProps | null>(null)

function useChart() {
  const context = React.useContext(ChartContext)

  if (!context) {
    throw new Error("useChart must be used within a <ChartContainer />")
  }

  return context
}

const ChartContainer = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div"> & {
    config: ChartConfig
    children: React.ComponentProps<
      typeof RechartsPrimitive.ResponsiveContainer
    >["children"]
  }
>(({ id, className, children, config, ...props }, ref) => {
  const uniqueId = React.useId()
  const chartId = `chart-${id || uniqueId.replace(/:/g, "")}`

  return (
    <ChartContext.Provider value={{ config }}>
      <div
        data-chart={chartId}
        ref={ref}
        className={cn(
          "flex aspect-video justify-center text-xs [&_.recharts-cartesian-axis-tick_text]:fill-muted-foreground [&_.recharts-cartesian-grid_line]:stroke-border/50 [&_.recharts-curve.recharts-tooltip-cursor]:stroke-border [&_.recharts-polar-grid_[stroke='#ccc']]:stroke-border [&_.recharts-radial-bar-background-sector]:fill-muted [&_.recharts-rectangle.recharts-tooltip-cursor]:fill-muted [&_.recharts-reference-line_[stroke='#ccc']]:stroke-border [&_.recharts-sector[stroke='#fff']]:stroke-transparent [&_.recharts-sector]:outline-none [&_.recharts-surface]:outline-none",
          className
        )}
        {...props}
      >
        <ChartStyle id={chartId} config={config} />
        <RechartsPrimitive.ResponsiveContainer>
          {children}
        </RechartsPrimitive.ResponsiveContainer>
      </div>
    </ChartContext.Provider>
  )
})
ChartContainer.displayName = "Chart"

const ChartStyle = ({ id, config }: { id: string; config: ChartConfig }) => {
  const colorConfig = Object.entries(config).filter(
    ([, item]) => item.theme || item.color
  )

  if (!colorConfig.length) {
    return null
  }

  return (
    <style
      dangerouslySetInnerHTML={{
        __html: Object.entries({
          light: "",
          dark: ".dark",
        })
          .map(
            ([theme, prefix]) => `
${prefix} [data-chart=${id}] {
${colorConfig
  .map(([key, itemConfig]) => {
    const color =
      itemConfig.theme?.[theme as keyof typeof itemConfig.theme] ||
      itemConfig.color
    return color ? `  --color-${key}: ${color};` : null
  })
  .join("\n")}
}
`
          )
          .join("\n"),
      }}
    />
  )
}

const ChartTooltip = RechartsPrimitive.Tooltip

type TooltipPayloadItem = {
  dataKey?: string | number
  name?: string
  value?: number
  payload?: Record<string, unknown>
  color?: string
  [k: string]: unknown
}

const ChartTooltipContent = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div"> & {
    hideLabel?: boolean
    hideIndicator?: boolean
    indicator?: "line" | "dot" | "dashed"
    reportPayer?: boolean
    className?: string
    config?: symbol
    children?: React.ReactNode
  } & {
    // Runtime tooltip render props supplied by Recharts (not part of the
    // static Tooltip prop types in v3).
    active?: boolean
    payload?: unknown
    label?: unknown
    labelFormatter?: (label: unknown, payload: unknown) => React.ReactNode
  }
>((props, ref) => {
  const { config } = useChart()
  const { className, indicator = "dot", payload, label, labelFormatter } = props as {
    className?: string
    indicator?: "line" | "dot" | "dashed"
    payload?: unknown
    label?: unknown
    labelFormatter?: (label: unknown, payload: unknown) => React.ReactNode
  }

  if (!payload || !Array.isArray(payload) || payload.length === 0) {
    return null
  }

  const items = payload as unknown as TooltipPayloadItem[]

  return (
    <div
      ref={ref}
      className={cn(
        "grid min-w-[8rem] items-start gap-1.5 rounded-lg border border-border/50 bg-background px-2.5 py-1.5 text-xs shadow-xl",
        className
      )}
    >
      {label ? (
        <div className="font-medium">
          {labelFormatter ? labelFormatter(label, payload) : String(label)}
        </div>
      ) : null}
      <div className="grid gap-1.5">
        {items.map((item) => {
          const itemConfig = config[String(item.dataKey)] ?? config[String(item.name)]
          const indicatorColor: string =
            (typeof item.color === "string" ? item.color : undefined) ??
            (typeof item.payload?.fill === "string" ? item.payload.fill : undefined) ??
            "currentColor"
          const value = item.value ?? (item.payload ? item.payload[String(item.dataKey)] : undefined)

          return (
            <div
              key={String(item.dataKey ?? item.name)}
              className="flex items-center gap-2"
            >
              {indicator !== "line" ? (
                <span
                  className={cn(
                    "size-2.5 shrink-0 rounded-full",
                    indicator === "dot" && "bg-(--color-indicator)",
                    indicator === "dashed" && "w-3.5 rounded-[2px] border border-dashed bg-transparent"
                  )}
                  style={{ ["--color-indicator" as string]: indicatorColor }}
                />
              ) : (
                <span className="h-3 w-1 rounded-full" style={{ background: indicatorColor }} />
              )}
              <span className="text-muted-foreground">
                {itemConfig?.label ?? item.name ?? item.dataKey}
              </span>
              <span className="ml-auto font-mono font-medium tabular-nums text-foreground">
                {typeof value === "number" ? value.toLocaleString() : String(value ?? "")}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
})
ChartTooltipContent.displayName = "ChartTooltip"

export {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
}