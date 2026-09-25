import type { ChartTimeframe, Timeframe } from "@/lib/types";

/** Timeframes the backend supports for OHLC (biquote M1–D1). */
export const CHART_TIMEFRAMES: Timeframe[] = ["M1", "M5", "M15", "H1", "H4", "D1"];

/**
 * Timeframes exposed in the trading UI. Weekly and monthly are served by
 * aggregating daily candles client-side (biquote only retains M1–D1).
 */
export const MARKET_TIMEFRAMES: Array<{ value: ChartTimeframe; label: string }> = [
  { value: "M1", label: "1m" },
  { value: "M5", label: "5m" },
  { value: "M15", label: "15m" },
  { value: "M30", label: "30m" },
  { value: "H1", label: "1H" },
  { value: "H4", label: "4H" },
  { value: "D1", label: "1D" },
  { value: "W1", label: "1W" },
  { value: "MN", label: "1M" },
];

/** Map a chart timeframe to the backend interval to fetch (W1/MN build on D1). */
export const TIMEFRAME_SOURCE: Record<ChartTimeframe, Timeframe> = {
  M1: "M1",
  M5: "M5",
  M15: "M15",
  M30: "M30",
  H1: "H1",
  H4: "H4",
  D1: "D1",
  W1: "D1",
  MN: "D1",
};

/** Default multi-timeframe set used for an analysis cycle. */
export const ANALYSIS_TIMEFRAMES: Timeframe[] = ["M5", "H1", "H4"];

export const DEFAULT_SYMBOLS = ["XAUUSD", "BTCUSD"];

export interface AgentMeta {
  id: string;
  name: string;
  role: string;
  description: string;
  accent: string;
  logo: string;
}

export const AGENTS: AgentMeta[] = [
  {
    id: "technical_analyst",
    name: "Technical Analyst",
    role: "Market Analysis",
    description: "Price action, indicators and the ML ensemble.",
    accent: "#eab308",
    logo: "/agents/technical_analyst.jpg",
  },
  {
    id: "news_monitor",
    name: "News Monitor",
    role: "Sentiment",
    description: "Macro calendar, headlines and event impact.",
    accent: "#f97316",
    logo: "/agents/news_monitor.jpg",
  },
  {
    id: "risk_manager",
    name: "Risk Manager",
    role: "Risk Control",
    description: "VaR, position sizing and veto authority.",
    accent: "#ef4444",
    logo: "/agents/risk_manager.jpg",
  },
  {
    id: "decision_maker",
    name: "Decision Maker",
    role: "Final Judgment",
    description: "Weighted consensus vote and execution.",
    accent: "#22c55e",
    logo: "/agents/decision_maker.jpg",
  },
];

export function agentName(id: string): string {
  return AGENTS.find((agent) => agent.id === id)?.name ?? id;
}

export function agentMeta(id: string): AgentMeta | undefined {
  return AGENTS.find((agent) => agent.id === id);
}

export const SIGNAL_DIRECTIONS = ["BULLISH", "BEARISH", "NEUTRAL"] as const;
export const DECISIONS = ["BUY", "SELL", "WAIT", "SKIP"] as const;
