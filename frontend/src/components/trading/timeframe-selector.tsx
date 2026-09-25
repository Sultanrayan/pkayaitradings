"use client";

import { useMarketContext } from "@/components/symbol-provider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { MARKET_TIMEFRAMES } from "@/lib/constants";

/**
 * Timeframe control around the chart. Renders a segmented bar on desktop and a
 * dropdown on small screens; always keeps the selected timeframe active.
 */
export function TimeframeSelector() {
  const { timeframe, setTimeframe } = useMarketContext();

  return (
    <div className="flex items-center gap-2">
      <div className="hidden items-center gap-0.5 rounded-lg border border-border bg-card p-0.5 sm:flex">
        {MARKET_TIMEFRAMES.map((item) => {
          const active = item.value === timeframe;
          return (
            <button
              key={item.value}
              type="button"
              onClick={() => setTimeframe(item.value)}
              aria-pressed={active}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                active
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              }`}
            >
              {item.label}
            </button>
          );
        })}
      </div>

      <div className="sm:hidden">
        <Select value={timeframe} onValueChange={(value) => setTimeframe(value as typeof timeframe)}>
          <SelectTrigger className="w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MARKET_TIMEFRAMES.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}