"use client";

import { ChevronDown, LineChart } from "lucide-react";
import { cn } from "cn";

import type { ChartOverlays } from "@/components/charts/price-chart";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export const OVERLAY_LABELS: Array<{ key: keyof ChartOverlays; label: string; color: string }> = [
  { key: "ema20", label: "EMA 20", color: "#eab308" },
  { key: "ema50", label: "EMA 50", color: "#3b82f6" },
  { key: "ema200", label: "EMA 200", color: "#a855f7" },
  { key: "bollinger", label: "Bollinger", color: "#52525b" },
  { key: "volume", label: "Volume", color: "#71717a" },
];

export const INDICATOR_ITEMS = [
  { key: "rsi", label: "RSI" },
  { key: "macd", label: "MACD" },
  { key: "atr", label: "ATR" },
  { key: "stochastic", label: "Stochastic" },
] as const;

export type IndicatorKey = (typeof INDICATOR_ITEMS)[number]["key"];

/**
 * Dropdown-only indicators control. Overlays and indicator panes are toggled
 * here; nothing is shown on the chart until an item is checked. The menu only
 * appears when the trigger is clicked.
 */
export function IndicatorsMenu({
  overlays,
  indicators,
  onToggleOverlay,
  onToggleIndicator,
}: {
  overlays: ChartOverlays;
  indicators: Record<IndicatorKey, boolean>;
  onToggleOverlay: (key: keyof ChartOverlays) => void;
  onToggleIndicator: (key: IndicatorKey) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="Indicators"
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-card px-2.5 text-xs font-medium text-foreground transition-colors hover:bg-accent"
        >
          <LineChart className="size-3.5 text-muted-foreground" />
          Indicators
          <ChevronDown className="size-3.5 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuLabel>Overlays</DropdownMenuLabel>
        {OVERLAY_LABELS.map((overlay) => (
          <DropdownMenuCheckboxItem
            key={overlay.key}
            checked={overlays[overlay.key]}
            onCheckedChange={() => onToggleOverlay(overlay.key)}
          >
            <span className="flex items-center gap-2">
              <span className="size-2 rounded-full" style={{ background: overlay.color }} />
              {overlay.label}
            </span>
          </DropdownMenuCheckboxItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Panes</DropdownMenuLabel>
        {INDICATOR_ITEMS.map((indicator) => (
          <DropdownMenuCheckboxItem
            key={indicator.key}
            checked={indicators[indicator.key]}
            onCheckedChange={() => onToggleIndicator(indicator.key)}
          >
            <span
              className={cn(
                "flex items-center gap-2",
                indicators[indicator.key] && "font-medium",
              )}
            >
              {indicator.label}
            </span>
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}