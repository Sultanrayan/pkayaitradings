"use client";

import { useMemo, useState } from "react";
import { Search, Star } from "lucide-react";
import { cn } from "cn";

import { useMarketContext } from "@/components/symbol-provider";
import { Input } from "@/components/ui/input";
import { useWatchlist } from "@/hooks/use-watchlist";
import { formatPrice } from "@/lib/format";
import type { Tick } from "@/lib/types";

/**
 * Asset selector: search + favourite list. Selecting an asset updates the
 * chart while preserving the selected timeframe. `onSelect` is called after
 * an asset is chosen (used by dropdown wrappers to close the menu).
 */
export function AssetPicker({
  onSelect,
  assets,
}: {
  onSelect?: () => void;
  assets?: string[];
}) {
  const { symbols: contextSymbols, symbol, setSymbol, ticks } = useMarketContext();
  const { symbols: watched, toggle, contains } = useWatchlist();
  const [query, setQuery] = useState("");
  const symbols = assets ?? contextSymbols;

  const normalized = query.trim().toUpperCase();

  const filtered = useMemo(() => {
    if (!normalized) return symbols;
    return symbols.filter((item) => item.includes(normalized));
  }, [symbols, normalized]);

  const pick = (item: string) => {
    setSymbol(item);
    onSelect?.();
  };

  const favouriteAssets = symbols.filter((item) => watched.includes(item));

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search assets…"
          className="pl-8"
        />
      </div>

      {favouriteAssets.length > 0 ? (
        <div className="space-y-1">
          <div className="px-1 text-[10px] uppercase tracking-wider text-muted-foreground">
            Favourites
          </div>
          {favouriteAssets.map((item) => (
            <AssetRow key={item} item={item} ticks={ticks} active={item === symbol} onSelect={pick} onToggle={toggle} watched />
          ))}
        </div>
      ) : null}

      <div className="space-y-1">
        <div className="px-1 text-[10px] uppercase tracking-wider text-muted-foreground">
          All assets
        </div>
        {filtered.map((item) => (
          <AssetRow key={item} item={item} ticks={ticks} active={item === symbol} onSelect={pick} onToggle={toggle} watched={contains(item)} />
        ))}
        {filtered.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
            No assets match “{query}”.
          </div>
        ) : null}
      </div>
    </div>
  );
}

function AssetRow({
  item,
  ticks,
  active,
  onSelect,
  onToggle,
  watched,
}: {
  item: string;
  ticks: Record<string, Tick>;
  active: boolean;
  onSelect: (symbol: string) => void;
  onToggle: (symbol: string) => void;
  watched: boolean;
}) {
  const tick = ticks[item];
  const change = tick?.dayDiffPercent ?? null;
  return (
    <div
      className={cn(
        "group flex items-center gap-2 rounded-lg border border-transparent px-2 py-1.5 transition-colors hover:bg-accent/50",
        active && "bg-accent",
      )}
    >
      <button
        type="button"
        onClick={() => onSelect(item)}
        className="flex min-w-0 flex-1 items-center gap-2 text-left"
      >
        <span className="text-sm font-medium">{item}</span>
        <span className="truncate text-[11px] text-muted-foreground">{tick?.description ?? ""}</span>
        <span className="ml-auto tabular text-xs text-muted-foreground">{formatPrice(tick?.mid)}</span>
        {change !== null ? (
          <span className={cn("tabular text-[11px]", change >= 0 ? "text-bull" : "text-bear")}>
            {change >= 0 ? "+" : ""}
            {change.toFixed(2)}%
          </span>
        ) : null}
      </button>
      <button
        type="button"
        aria-label={`Toggle ${item} favourite`}
        onClick={() => onToggle(item)}
        className={cn(
          "rounded p-1 transition-colors hover:bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          watched ? "text-gold" : "text-muted-foreground opacity-0 group-hover:opacity-100",
        )}
      >
        <Star className={cn("size-3.5", watched && "fill-gold")} />
      </button>
    </div>
  );
}