"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, Star } from "lucide-react";
import { cn } from "cn";

import { useMarketContext } from "@/components/symbol-provider";
import { PageHeader } from "@/components/shared/primitives";
import { Input } from "@/components/ui/input";
import { useWatchlist } from "@/hooks/use-watchlist";
import { formatPrice, formatSignedPercent } from "@/lib/format";

/**
 * Market page: browse, search and select assets. Selecting an asset opens its
 * detailed chart view (routes to the dashboard chart for that asset).
 */
export function MarketView() {
  const { symbols, symbol, setSymbol, ticks } = useMarketContext();
  const { symbols: watched, toggle } = useWatchlist();
  const router = useRouter();
  const [query, setQuery] = useState("");

  const normalized = query.trim().toUpperCase();
  const assets = useMemo(
    () => (normalized ? symbols.filter((item) => item.includes(normalized)) : symbols),
    [symbols, normalized],
  );

  const openAsset = (item: string) => {
    setSymbol(item);
    router.push("/dashboard");
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Market"
        description="Browse available markets, search for an asset and open its detailed chart."
      />

      <div className="relative max-w-md">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search assets…"
          className="pl-9"
        />
      </div>

      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {assets.map((item) => {
          const tick = ticks[item];
          const change = tick?.dayDiffPercent ?? null;
          const active = item === symbol;
          return (
            <div
              key={item}
              className={cn(
                "group rounded-xl border p-4 transition-colors",
                active ? "border-foreground/40 bg-card" : "border-border bg-card hover:border-foreground/25",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold">{item}</span>
                  <span className="truncate text-[11px] text-muted-foreground">
                    {tick?.description ?? ""}
                  </span>
                </div>
                <button
                  type="button"
                  aria-label={`Toggle ${item} favourite`}
                  onClick={() => toggle(item)}
                  className={cn(
                    "rounded p-1 text-muted-foreground transition-colors hover:bg-accent",
                    watched.includes(item) && "text-gold",
                  )}
                >
                  <Star className={cn("size-4", watched.includes(item) && "fill-gold")} />
                </button>
              </div>

              <div className="mt-3 flex items-end justify-between gap-2">
                <span className="tabular text-xl font-semibold">{formatPrice(tick?.mid)}</span>
                <span className={cn("tabular text-xs font-medium", change === null ? "text-muted-foreground" : change >= 0 ? "text-bull" : "text-bear")}>
                  {formatSignedPercent(change)}
                </span>
              </div>

              <div className="mt-4">
                <button
                  type="button"
                  onClick={() => openAsset(item)}
                  className="w-full rounded-lg border border-border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-accent hover:text-foreground"
                >
                  Open chart
                </button>
              </div>
            </div>
          );
        })}
        {assets.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground sm:col-span-2 xl:col-span-3">
            No assets match “{query}”.
          </div>
        ) : null}
      </div>
    </div>
  );
}