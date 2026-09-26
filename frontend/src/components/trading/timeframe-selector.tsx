"use client";

import { ChevronDown } from "lucide-react";

import { useMarketContext } from "@/components/symbol-provider";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MARKET_TIMEFRAMES } from "@/lib/constants";

/**
 * TradingView-style timeframe control: a single trigger that reveals the
 * timeframe menu only when clicked. Preserves the selected asset.
 */
export function TimeframeSelector() {
  const { timeframe, setTimeframe } = useMarketContext();
  const active = MARKET_TIMEFRAMES.find((item) => item.value === timeframe);
  const label = active?.label ?? timeframe;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="Change timeframe"
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-card px-2.5 text-xs font-medium text-foreground transition-colors hover:bg-accent"
        >
          {label}
          <ChevronDown className="size-3.5 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-28">
        <DropdownMenuLabel>Timeline</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {MARKET_TIMEFRAMES.map((item) => {
          const activeItem = item.value === timeframe;
          return (
            <DropdownMenuItem
              key={item.value}
              onSelect={() => setTimeframe(item.value)}
              className={activeItem ? "bg-accent font-medium" : undefined}
            >
              <span className="flex w-full items-center justify-between gap-4">
                {item.label}
                {activeItem ? <span className="size-1.5 rounded-full bg-foreground" /> : null}
              </span>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}