"use client";

import { useMemo, useSyncExternalStore } from "react";

import { useMarketContext } from "@/components/symbol-provider";
import { useNow } from "@/hooks/use-now";
import {
  demoAssetSymbols,
  generateDemoCandles,
  generateDemoSignals,
  generateDemoTick,
} from "@/lib/demo-data";
import type { ChartTimeframe, OhlcSeries, SignalRecord, Tick } from "@/lib/types";

/**
 * Demo mode: returns synthetic market data so the UI is viewable without a
 * running backend. Activated by `NEXT_PUBLIC_DEMO_MODE=true`, or per-session
 * with `?demo=1`.
 *
 * The query-string flag is read through an external store rather than during
 * render. `window.location` is unavailable on the server, so reading it inline
 * would make the first client render disagree with the server HTML.
 */
let queryDemo = false;
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (typeof window !== "undefined" && !queryDemo) {
    queryDemo = new URLSearchParams(window.location.search).get("demo") === "1";
    if (queryDemo) for (const item of listeners) item();
  }
  return () => {
    listeners.delete(listener);
  };
}

export function useDemoMode(): boolean {
  const fromQuery = useSyncExternalStore(
    subscribe,
    () => queryDemo,
    () => false,
  );
  return process.env.NEXT_PUBLIC_DEMO_MODE === "true" || fromQuery;
}

export interface DemoMarket {
  symbols: string[];
  series: OhlcSeries;
  signals: SignalRecord[];
  tick: Tick;
}

/**
 * Build a complete demo market snapshot for the current symbol/timeframe.
 *
 * `now` comes from the shared hydration-safe clock, so the very first render
 * (server and client) produces byte-identical synthetic data and only starts
 * ticking after hydration.
 */
export function useDemoMarket(demo: boolean, timeframe: ChartTimeframe): DemoMarket | null {
  const { symbol } = useMarketContext();
  const now = useNow();

  // Series + signals are stable per (symbol, timeframe); only the tick moves.
  const staticPart = useMemo(() => {
    if (!demo) return null;
    const count = timeframe === "W1" || timeframe === "MN" ? 320 : timeframe === "D1" ? 360 : 300;
    return {
      symbols: demoAssetSymbols(),
      series: {
        symbol,
        interval: timeframe,
        bars: generateDemoCandles(symbol, timeframe, count, now),
      },
      signals: generateDemoSignals(symbol, timeframe, 40, now),
    };
  }, [demo, symbol, timeframe, now]);

  return useMemo<DemoMarket | null>(() => {
    if (!staticPart || !demo) return null;
    return {
      ...staticPart,
      tick: generateDemoTick(symbol, now),
    };
  }, [staticPart, demo, symbol, now]);
}