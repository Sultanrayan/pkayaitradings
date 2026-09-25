"use client";

import { Star } from "lucide-react";
import { cn } from "cn";

import { useMarketContext } from "@/components/symbol-provider";
import { useWatchlist } from "@/hooks/use-watchlist";
import { formatPrice, formatSignedPercent } from "@/lib/format";

/** Asset header: symbol, price, change, market status and favourite toggle. */
export function AssetHeader() {
  const { symbol, activeTick, status } = useMarketContext();
  const { contains, toggle } = useWatchlist();
  const tick = activeTick;
  const watched = contains(symbol);

  const change = tick?.dayDiffPercent ?? null;
  const tone = change === null ? "flat" : change >= 0 ? "bull" : "bear";
  const marketState = tick?.marketState ?? "unknown";

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-border bg-card px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="text-lg font-semibold tracking-tight">{symbol.replace(/(USD|EUR)$/, "/$1")}</span>
        {tick?.description ? (
          <span className="text-xs text-muted-foreground">{tick.description}</span>
        ) : null}
      </div>

      <div className="flex items-center gap-3">
        <span className="text-2xl font-semibold tabular">{formatPrice(tick?.mid)}</span>
        <span className={cn("tabular text-sm font-medium", tone === "bull" ? "text-bull" : tone === "bear" ? "text-bear" : "text-muted-foreground")}>
          {formatSignedPercent(change)}
        </span>
      </div>

      <div className="flex items-center gap-2 text-xs">
        <span
          className={cn(
            "rounded-full px-2 py-0.5 uppercase tracking-wider ring-1",
            marketState === "open"
              ? "bg-bull/10 text-bull ring-bull/30"
              : marketState === "closed"
                ? "bg-muted text-muted-foreground ring-border"
                : "bg-muted text-muted-foreground ring-border",
          )}
        >
          {marketState}
        </span>
        {status === "live" ? (
          <span className="text-muted-foreground">· live</span>
        ) : null}
      </div>

      <button
        type="button"
        aria-label={watched ? "Remove from watchlist" : "Add to watchlist"}
        onClick={() => toggle(symbol)}
        className={cn(
          "ml-auto rounded-md p-1.5 outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring",
          watched ? "text-gold" : "text-muted-foreground",
        )}
      >
        <Star className={cn("size-4", watched && "fill-gold")} />
      </button>
    </div>
  );
}