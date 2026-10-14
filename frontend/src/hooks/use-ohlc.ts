"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { aggregateOhlc } from "@/lib/aggregate";
import { TIMEFRAME_SOURCE } from "@/lib/constants";
import type { ChartTimeframe, OhlcBar, OhlcSeries } from "@/lib/types";

/**
 * Make a fetched series safe to hand to the chart library.
 *
 * biquote serves a *sliding* intraday window, and short intervals (M1/M5/M15)
 * are the ones where that window turns over fastest — so a response can arrive
 * with duplicate or out-of-order timestamps while a timeframe switch is in
 * flight. Lightweight Charts asserts that series are strictly ascending and
 * unique by time, and throws otherwise, which is what produced the crash when
 * moving between 15m / 5m / 1m. Normalising here fixes it for every consumer.
 */
function normaliseBars(bars: OhlcBar[]): OhlcBar[] {
  const byTime = new Map<number, OhlcBar>();
  for (const bar of bars) {
    const time = new Date(bar.openTime).getTime();
    if (!Number.isFinite(time)) continue;
    if (
      !Number.isFinite(bar.open) ||
      !Number.isFinite(bar.high) ||
      !Number.isFinite(bar.low) ||
      !Number.isFinite(bar.close)
    ) {
      continue;
    }
    // Later wins, so an in-progress bar updated by a later fetch replaces
    // the stale copy from the previous one.
    byTime.set(time, bar);
  }
  return [...byTime.entries()].sort(([a], [b]) => a - b).map(([, bar]) => bar);
}

export interface OhlcState {
  series: OhlcSeries | null;
  loading: boolean;
  error: string | null;
}

interface InternalState {
  key: string;
  series: OhlcSeries | null;
  error: string | null;
}

/** Fetch OHLC candles whenever the symbol or timeframe changes. */
export function useOhlc(symbol: string, timeframe: ChartTimeframe, limit = 240): OhlcState {
  const key = `${symbol}:${timeframe}:${limit}`;
  const [state, setState] = useState<InternalState>({ key: "", series: null, error: null });

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const source = TIMEFRAME_SOURCE[timeframe];
        const requested = timeframe === "W1" || timeframe === "MN" ? 1000 : limit;
        const data = await api.ohlc(symbol, source, requested);
        const raw = timeframe === "W1" || timeframe === "MN" ? aggregateOhlc(data, timeframe) : data;
        const series: OhlcSeries = { ...raw, bars: normaliseBars(raw.bars) };
        if (!controller.signal.aborted) setState({ key, series, error: null });
      } catch (cause) {
        if (!controller.signal.aborted) {
          setState({
            key,
            series: null,
            error: cause instanceof Error ? cause.message : "Failed to load candles",
          });
        }
      }
    })();
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, symbol, timeframe]);

  const settled = state.key === key;
  return {
    // Never expose another timeframe's candles under a new label while the
    // switch is in flight — the chart would otherwise mix two series.
    series: settled ? state.series : null,
    error: settled ? state.error : null,
    loading: !settled,
  };
}