"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { aggregateOhlc } from "@/lib/aggregate";
import { TIMEFRAME_SOURCE } from "@/lib/constants";
import type { ChartTimeframe, OhlcSeries } from "@/lib/types";

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
        const series =
          timeframe === "W1" || timeframe === "MN" ? aggregateOhlc(data, timeframe) : data;
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
    series: state.series,
    error: settled ? state.error : null,
    loading: !settled,
  };
}