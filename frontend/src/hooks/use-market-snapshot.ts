"use client";

import { useMemo } from "react";
import { generateDemoTick } from "@/lib/demo-data";
import { useMarketContext } from "@/components/symbol-provider";
import { useNow } from "@/hooks/use-now";

export interface MarketSnapshot {
  price: number;
  change: number;
  source: "live" | "demo";
}

/**
 * Market snapshot for an attachment. Uses the live tick stream when available;
 * otherwise produces a deterministic demo tick (refreshed every 1.5s) so the
 * attachment always renders real-looking numbers.
 */
export function useMarketSnapshot(symbol: string): MarketSnapshot {
  const now = useNow(1_500);
  const { ticks } = useMarketContext();

  return useMemo<MarketSnapshot>(() => {
    const live = ticks[symbol];
    if (live && typeof live.mid === "number") {
      return { price: live.mid, change: live.dayDiffPercent ?? 0, source: "live" };
    }
    const demo = generateDemoTick(symbol, now);
    return {
      price: demo.mid,
      change: demo.dayDiffPercent ?? 0,
      source: "demo",
    };
  }, [symbol, ticks, now]);
}