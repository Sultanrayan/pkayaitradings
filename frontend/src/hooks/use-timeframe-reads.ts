"use client";

import { useCallback } from "react";

import { useAsyncData } from "@/hooks/use-async-data";
import { api } from "@/lib/api";
import { TIMEFRAME_SOURCE } from "@/lib/constants";
import { biasFromBars, type Bias } from "@/lib/market-intel";
import type { ChartTimeframe, OhlcBar } from "@/lib/types";

export interface FrameRead {
  bias: Bias;
  score: number;
  loading: boolean;
}

/** Timeframes shown in the multi-timeframe strip. */
export const MTF_TIMEFRAMES: ChartTimeframe[] = ["M5", "M15", "H1", "H4", "D1"];

const LABELS: Record<string, string> = {
  M5: "5M",
  M15: "15M",
  H1: "1H",
  H4: "4H",
  D1: "1D",
};

/**
 * Per-timeframe structural read for the multi-timeframe row.
 *
 * Batched into one request so switching timeframes on the chart does not cost
 * extra round-trips. In demo mode the caller passes generated bars.
 */
export function useTimeframeReads(
  symbol: string,
  demo: boolean,
  demoBars?: (timeframe: ChartTimeframe) => OhlcBar[],
): Record<string, FrameRead> {
  const key = `mtf:${symbol}:${demo ? "demo" : "live"}`;
  const loader = useCallback(async (): Promise<Record<string, FrameRead>> => {
    if (demo) {
      const result: Record<string, FrameRead> = {};
      for (const timeframe of MTF_TIMEFRAMES) {
        const bars = demoBars?.(timeframe) ?? [];
        result[timeframe] = { ...biasFromBars(bars), loading: false };
      }
      return result;
    }
    const series = await Promise.all(
      MTF_TIMEFRAMES.map(async (timeframe) => {
        try {
          const data = await api.ohlc(symbol, TIMEFRAME_SOURCE[timeframe], 120);
          return [timeframe, data.bars] as const;
        } catch {
          return [timeframe, [] as OhlcBar[]] as const;
        }
      }),
    );
    const result: Record<string, FrameRead> = {};
    for (const [timeframe, bars] of series) {
      result[timeframe] = { ...biasFromBars(bars), loading: false };
    }
    return result;
  }, [symbol, demo, demoBars]);

  const { data } = useAsyncData(key, loader, {} as Record<string, FrameRead>);

  const reads: Record<string, FrameRead> = {};
  for (const timeframe of MTF_TIMEFRAMES) {
    reads[timeframe] = data[timeframe] ?? { bias: "Neutral", score: 0.5, loading: true };
  }
  return reads;
}

export function timeframeLabel(timeframe: string): string {
  return LABELS[timeframe] ?? timeframe;
}
