"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { OhlcSeries, Timeframe } from "@/lib/types";

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
export function useOhlc(symbol: string, timeframe: Timeframe, limit = 240): OhlcState {
  const key = `${symbol}:${timeframe}:${limit}`;
  const [state, setState] = useState<InternalState>({ key: "", series: null, error: null });

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const data = await api.ohlc(symbol, timeframe, limit);
        if (!controller.signal.aborted) setState({ key, series: data, error: null });
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
  }, [key, symbol, timeframe, limit]);

  const settled = state.key === key;
  return {
    series: state.series,
    error: settled ? state.error : null,
    loading: !settled,
  };
}
