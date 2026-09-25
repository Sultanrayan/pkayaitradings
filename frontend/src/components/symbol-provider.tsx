"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { useTicks, type StreamStatus } from "@/hooks/use-ticks";
import { api } from "@/lib/api";
import { DEFAULT_SYMBOLS } from "@/lib/constants";
import type { Tick, Timeframe } from "@/lib/types";

interface SymbolContextValue {
  symbols: string[];
  symbol: string;
  setSymbol: (symbol: string) => void;
  timeframe: Timeframe;
  setTimeframe: (timeframe: Timeframe) => void;
  ticks: Record<string, Tick>;
  status: StreamStatus;
  lastUpdate: number | null;
  environment: string;
  activeTick?: Tick;
}

const SymbolContext = createContext<SymbolContextValue | null>(null);

export function SymbolProvider({ children }: { children: React.ReactNode }) {
  const [symbols, setSymbols] = useState<string[]>(DEFAULT_SYMBOLS);
  const [symbol, setSymbol] = useState(DEFAULT_SYMBOLS[0]);
  const [timeframe, setTimeframe] = useState<Timeframe>("H1");
  const [environment, setEnvironment] = useState("development");

  const { ticks, status, lastUpdate } = useTicks(symbols);

  useEffect(() => {
    let active = true;
    api
      .health()
      .then((health) => {
        if (!active) return;
        setEnvironment(health.environment);
        if (health.symbols.length) setSymbols(health.symbols);
      })
      .catch(() => {
        /* backend may still be starting */
      });
    return () => {
      active = false;
    };
  }, []);

  const handleSetSymbol = useCallback((next: string) => setSymbol(next.toUpperCase()), []);

  const value = useMemo<SymbolContextValue>(
    () => ({
      symbols,
      symbol,
      setSymbol: handleSetSymbol,
      timeframe,
      setTimeframe,
      ticks,
      status,
      lastUpdate,
      environment,
      activeTick: ticks[symbol],
    }),
    [symbols, symbol, handleSetSymbol, timeframe, ticks, status, lastUpdate, environment],
  );

  return <SymbolContext.Provider value={value}>{children}</SymbolContext.Provider>;
}

export function useMarketContext(): SymbolContextValue {
  const context = useContext(SymbolContext);
  if (!context) {
    throw new Error("useMarketContext must be used within a SymbolProvider");
  }
  return context;
}
