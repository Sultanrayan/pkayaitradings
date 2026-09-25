"use client";

import { useCallback, useState } from "react";

import { api } from "@/lib/api";
import type { CycleResponse, Position, Timeframe } from "@/lib/types";

export interface AnalysisState {
  cycle: CycleResponse | null;
  positions: Position[];
  equity: number | null;
  loading: boolean;
  error: string | null;
  lastRun: number | null;
  run: (symbol: string, timeframes: Timeframe[]) => Promise<void>;
  refreshAccount: () => Promise<void>;
}

/** Run analysis cycles and keep the paper-account summary in sync. */
export function useAnalysis(): AnalysisState {
  const [cycle, setCycle] = useState<CycleResponse | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [equity, setEquity] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<number | null>(null);

  const refreshAccount = useCallback(async () => {
    try {
      const [nextPositions, nextEquity] = await Promise.all([api.positions(), api.equity()]);
      setPositions(nextPositions);
      setEquity(nextEquity);
    } catch {
      // account summary is best-effort
    }
  }, []);

  const run = useCallback(
    async (symbol: string, timeframes: Timeframe[]) => {
      setLoading(true);
      setError(null);
      try {
        const result = await api.analyze(symbol, timeframes);
        setCycle(result);
        setLastRun(Date.now());
        await refreshAccount();
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Analysis failed");
      } finally {
        setLoading(false);
      }
    },
    [refreshAccount],
  );

  return { cycle, positions, equity, loading, error, lastRun, run, refreshAccount };
}
