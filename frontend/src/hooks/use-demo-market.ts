"use client";

import { useEffect, useMemo, useState } from "react";

import { useMarketContext } from "@/components/symbol-provider";
import {
  demoAssetSymbols,
  generateDemoCandles,
  generateDemoSignals,
  generateDemoTick,
} from "@/lib/demo-data";
import type { ChartTimeframe, OhlcSeries, SignalRecord, Tick } from "@/lib/types";

/**
 * Demo mode: returns synthetic market data so the UI is viewable without a
 * running backend. Activated by `?demo=1` or `NEXT_PUBLIC_DEMO_MODE=true`.
 */
export function useDemoMode(): boolean {
  const [demo] = useState<boolean>(() => {
    if (process.env.NEXT_PUBLIC_DEMO_MODE === "true") return true;
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("demo") === "1";
  });
  return demo;
}

export interface DemoMarket {
  symbols: string[];
  series: OhlcSeries;
  signals: SignalRecord[];
  tick: Tick;
}

/** Build a complete demo market snapshot for the current symbol/timeframe. */
export function useDemoMarket(demo: boolean, timeframe: ChartTimeframe): DemoMarket | null {
  const { symbol } = useMarketContext();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!demo) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1200);
    return () => window.clearInterval(timer);
  }, [demo]);

  // Series + signals are stable per (symbol, timeframe); only the tick moves.
  const staticPart = useMemo(() => {
    if (!demo) return null;
    const count = timeframe === "W1" || timeframe === "MN" ? 320 : timeframe === "D1" ? 360 : 300;
    return {
      symbols: demoAssetSymbols(),
      series: { symbol, interval: timeframe, bars: generateDemoCandles(symbol, timeframe, count) },
      signals: generateDemoSignals(symbol, timeframe, 40),
    };
  }, [demo, symbol, timeframe]);

  return useMemo<DemoMarket | null>(() => {
    if (!staticPart || !demo) return null;
    return {
      ...staticPart,
      tick: generateDemoTick(symbol, now),
    };
  }, [staticPart, demo, symbol, now]);
}