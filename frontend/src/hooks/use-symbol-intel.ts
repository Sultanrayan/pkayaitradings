"use client";

import { useCallback, useMemo } from "react";

import { useAsyncData } from "@/hooks/use-async-data";
import { api } from "@/lib/api";
import { TIMEFRAME_SOURCE } from "@/lib/constants";
import { deriveMarketIntel, type MarketIntel } from "@/lib/market-intel";
import type { ChartTimeframe, OhlcBar, SignalRecord } from "@/lib/types";

export interface SymbolIntel {
  bars: OhlcBar[];
  intel: MarketIntel | null;
  loading: boolean;
}

/** Cap the fan-out so a wide feed cannot flood the backend. */
const MAX_SYMBOLS = 4;

/**
 * Real candle data + derived conditions for the symbols visible in the feed.
 *
 * Cards read their mini chart, market conditions and key levels from actual
 * OHLC data (already available through `api.ohlc`) instead of synthesised
 * series. Symbols beyond `MAX_SYMBOLS` fall back to payload-only data.
 */
export function useSymbolIntel(
  symbols: string[],
  timeframe: ChartTimeframe,
  demo: boolean,
  demoBarsFor?: (timeframe: ChartTimeframe) => OhlcBar[],
  signalsFor?: (symbol: string) => SignalRecord[],
): Record<string, SymbolIntel> {
  const tracked = useMemo(
    () => [...new Set(symbols)].slice(0, MAX_SYMBOLS).sort(),
    [symbols],
  );
  const key = `symbol-intel:${tracked.join(",")}:${timeframe}:${demo ? "demo" : "live"}`;

  const loader = useCallback(async (): Promise<Record<string, SymbolIntel>> => {
    const result: Record<string, SymbolIntel> = {};

    await Promise.all(
      tracked.map(async (symbol) => {
        try {
          const bars =
            demo
              ? demoBarsFor?.(timeframe) ?? []
              : (await api.ohlc(symbol, TIMEFRAME_SOURCE[timeframe], 120)).bars;
          const records = signalsFor?.(symbol) ?? [];
          result[symbol] = {
            bars,
            intel: bars.length ? deriveMarketIntel(bars, records, records[0] ?? null) : null,
            loading: false,
          };
        } catch {
          result[symbol] = { bars: [], intel: null, loading: false };
        }
      }),
    );

    return result;
  }, [tracked, timeframe, demo, demoBarsFor, signalsFor]);

  const { data } = useAsyncData(key, loader, {} as Record<string, SymbolIntel>);

  const reads: Record<string, SymbolIntel> = {};
  for (const symbol of tracked) {
    reads[symbol] = data[symbol] ?? { bars: [], intel: null, loading: true };
  }
  return reads;
}
