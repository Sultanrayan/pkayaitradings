"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";

import { AssetPicker } from "@/components/trading/asset-picker";
import { useMarketContext } from "@/components/symbol-provider";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/** Format a symbol as a pair, e.g. XAUUSD → XAU/USD. Keeps unknown symbols intact. */
export function pairLabel(symbol: string): string {
  const match = symbol.match(/^([A-Z0-9]+?)(USD|EUR|GBP|JPY|AUD|CAD|CHF)$/i);
  return match ? `${match[1].toUpperCase()}/${match[2].toUpperCase()}` : symbol;
}

/**
 * TradingView-style pair selector: a single trigger that reveals the asset
 * search/list/favourites menu only when clicked, closing after a pick.
 */
export function PairSelector() {
  const { symbol } = useMarketContext();
  const [open, setOpen] = useState(false);

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="Change pair"
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-card px-2.5 text-sm font-semibold transition-colors hover:bg-accent"
        >
          {pairLabel(symbol)}
          <ChevronDown className="size-3.5 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-72">
        <DropdownMenuLabel>Markets</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <div className="p-1">
          <AssetPicker onSelect={() => setOpen(false)} />
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}