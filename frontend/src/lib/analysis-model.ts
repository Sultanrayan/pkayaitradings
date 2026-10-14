/**
 * Analysis insight model.
 *
 * Normalises a stored backend signal into the record the feed renders.
 *
 * The Decision Maker agent's output is surfaced as an explicit trade signal:
 * its `BUY` / `SELL` / `WAIT` decision is preserved verbatim and published
 * alongside the entry, target and take-profit levels the backend already
 * calculates in `TradeDecision`. Every other agent keeps the market-bias
 * reading (Bullish / Bearish / Neutral), because those agents emit a
 * `Direction`, not a `Decision`.
 *
 * The backend supplies `symbol`, `kind`, `direction`, `confidence`,
 * `created_at` and a free-form `payload`. Fields the backend does not populate
 * resolve to null or a neutral default here.
 */

import { directionTone } from "@/lib/format";
import type { SignalRecord } from "@/lib/types";

export const ANALYSIS_TYPES = [
  "All",
  "Technical",
  "News",
  "Market Structure",
  "Sentiment",
  "AI Consensus",
] as const;

export const AGENT_FILTERS = [
  "All",
  "Technical Analyst",
  "News Monitor",
  "Market Structure Analyst",
  "Sentiment Analyst",
  "AI Consensus",
] as const;

export const SIGNAL_TIMEFRAMES = ["M5", "M15", "H1", "H4", "D1"] as const;

export type AnalysisType = (typeof ANALYSIS_TYPES)[number];
export type AgentLabel = (typeof AGENT_FILTERS)[number];
export type Bias = "Bullish" | "Bearish" | "Neutral";

/**
 * The Decision Maker's explicit call, preserved from the backend `Decision`
 * enum. `WAIT` is a real decision — the model declining to take a position —
 * and is shown as such rather than being flattened into "Neutral".
 */
export type Recommendation = "BUY" | "SELL" | "WAIT";

/** Shape every feed card renders — see the product data contract. */
export interface AnalysisInsight {
  id: string;
  symbol: string;
  timeframe: string | null;
  analysisType: AnalysisType;
  agent: AgentLabel;
  agentDescription: string;
  bias: Bias;
  /** Trade signal from the Decision Maker; null for agents that emit a bias. */
  recommendation: Recommendation | null;
  entryPrice: number | null;
  takeProfit: number | null;
  stopLoss: number | null;
  riskApproved: boolean | null;
  confidence: number;
  summary: string | null;
  reasons: string[];
  trend: string | null;
  momentum: string | null;
  volatility: string | null;
  volume: string | null;
  resistance: number | null;
  currentPrice: number | null;
  support: number | null;
  timestamp: string;
}

const AGENT_LABELS: Record<string, AgentLabel> = {
  technical_analyst: "Technical Analyst",
  news_monitor: "News Monitor",
  risk_manager: "Market Structure Analyst",
  decision_maker: "AI Consensus",
};

const AGENT_DESCRIPTIONS: Partial<Record<AgentLabel, string>> = {
  "Technical Analyst": "Price action & indicators analysis",
  "News Monitor": "News & sentiment analysis",
  "Market Structure Analyst": "Structure, volatility & positioning",
  "Sentiment Analyst": "Sentiment & positioning analysis",
  "AI Consensus": "Weighted multi-agent view",
};

/**
 * Map a raw direction onto a market bias.
 *
 * Backend directions include execution-flavoured values (BUY / SELL / APPROVED
 * / WAIT / SKIP). Those are translated to their analytical meaning here and
 * never surfaced verbatim, so the feed cannot read as an execution product.
 */
export function toBias(direction: string | undefined): Bias {
  const value = (direction ?? "").toUpperCase();
  if (!value) return "Neutral";
  if (value.includes("BULL") || value.includes("UP") || value === "BUY") return "Bullish";
  if (value.includes("BEAR") || value.includes("DOWN") || value === "SELL") return "Bearish";
  return "Neutral";
}

/**
 * Preserve the Decision Maker's explicit call.
 *
 * Only Decision Maker records carry a `Decision`; every other agent emits a
 * `Direction` (or a risk verdict), so those return `null` and keep the bias
 * reading. `SKIP` is folded into `WAIT` — both mean the model declined to
 * recommend a trade, and splitting them would imply a distinction the backend
 * does not draw.
 */
export function toRecommendation(record: SignalRecord): Recommendation | null {
  if (record.agent !== "decision_maker") return null;
  const value = (record.direction ?? "").toUpperCase();
  if (value === "BUY" || value === "SELL") return value;
  if (value === "WAIT" || value === "SKIP") return "WAIT";
  return null;
}

function analysisTypeFor(record: SignalRecord): AnalysisType {
  const kind = record.kind.toLowerCase();
  const payload = record.payload as { sentiment?: string } | undefined;
  if (kind.includes("news")) return payload?.sentiment ? "Sentiment" : "News";
  if (kind.includes("technical")) return "Technical";
  if (kind.includes("risk")) return "Market Structure";
  if (kind.includes("decision")) return "AI Consensus";
  if (kind.includes("structure")) return "Market Structure";
  return "Technical";
}

function agentFor(record: SignalRecord): AgentLabel {
  const kind = record.kind.toLowerCase();
  const payload = record.payload as { sentiment?: string } | undefined;
  if (kind.includes("news") && payload?.sentiment) return "Sentiment Analyst";
  return AGENT_LABELS[record.agent] ?? "Technical Analyst";
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

/**
 * Reasons drawn straight from the payload when the backend supplies them.
 * Real indicator evidence replaces these at render time when candles load.
 */
function reasonsFromPayload(record: SignalRecord): string[] {
  const payload = record.payload as {
    indicators?: Record<string, unknown>;
    sentiment?: string;
    event?: string;
    alert?: string;
    reasoning?: string;
  };
  const reasons: string[] = [];

  if (payload.sentiment) {
    reasons.push(`Sentiment reading is ${String(payload.sentiment).replace(/_/g, " ").toLowerCase()}`);
  }
  if (payload.event) reasons.push(`Event: ${payload.event}`);
  if (payload.alert && payload.alert !== "NONE") {
    reasons.push(`Risk alert level: ${payload.alert.replace(/_/g, " ").toLowerCase()}`);
  }

  const indicators = payload.indicators ?? {};
  const rsi = asNumber(indicators.rsi);
  if (rsi !== null) {
    reasons.push(`RSI at ${rsi.toFixed(0)} is ${rsi >= 55 ? "firm" : rsi <= 45 ? "weakening" : "neutral"}`);
  }
  if (asNumber(indicators.macd_histogram) !== null) {
    const histogram = asNumber(indicators.macd_histogram) as number;
    reasons.push(`MACD momentum is ${histogram >= 0 ? "positive" : "negative"}`);
  }
  const emaCross = asText(indicators.ema_cross);
  if (emaCross) reasons.push(`EMA structure is ${emaCross.replace(/_/g, " ").toLowerCase()}`);

  return reasons.slice(0, 4);
}

/** Convert one stored signal into a feed-ready analytical record. */
export function toAnalysisInsight(
  record: SignalRecord,
  fallbackTimeframe: string,
): AnalysisInsight {
  const payload = record.payload as {
    key_levels?: { support?: number | null; resistance?: number | null };
    price?: number | null;
    entry_price?: number | null;
    take_profit?: number | null;
    stop_loss?: number | null;
    risk_approved?: boolean | null;
    timeframe?: string;
    reasoning?: string;
    trend?: string;
    momentum?: string;
    volatility?: string;
    volume?: string;
  };

  const keyLevels = payload.key_levels ?? {};
  const support = asNumber(keyLevels.support);
  const resistance = asNumber(keyLevels.resistance);
  const entryPrice = asNumber(payload.entry_price);
  const currentPrice = asNumber(payload.price) ?? entryPrice ?? null;

  const analysisType = analysisTypeFor(record);
  const agent = agentFor(record);
  const recommendation = toRecommendation(record);

  return {
    id: record.id,
    symbol: record.symbol,
    timeframe: asText(payload.timeframe) ?? fallbackTimeframe,
    analysisType,
    agent,
    agentDescription: AGENT_DESCRIPTIONS[agent] ?? "Market analysis",
    bias: toBias(record.direction),
    recommendation,
    entryPrice,
    takeProfit: asNumber(payload.take_profit),
    stopLoss: asNumber(payload.stop_loss),
    riskApproved:
      typeof payload.risk_approved === "boolean" ? payload.risk_approved : null,
    confidence: Math.min(Math.max(record.confidence, 0), 1),
    summary: asText(payload.reasoning),
    reasons: reasonsFromPayload(record),
    trend: asText(payload.trend),
    momentum: asText(payload.momentum),
    volatility: asText(payload.volatility),
    volume: asText(payload.volume),
    resistance,
    currentPrice,
    support,
    timestamp: record.created_at,
  };
}

/**
 * Overall bias across a set of insights, weighted by confidence. Used by the
 * AI consensus header.
 */
export function weightedBias(insights: AnalysisInsight[]): { bias: Bias; confidence: number } {
  const scored = insights.filter((insight) => insight.confidence > 0);
  if (!scored.length) return { bias: "Neutral", confidence: 0 };
  let total = 0;
  let weight = 0;
  for (const insight of scored) {
    const value = insight.bias === "Bullish" ? 1 : insight.bias === "Bearish" ? 0 : 0.5;
    total += value * insight.confidence;
    weight += insight.confidence;
  }
  const score = weight === 0 ? 0.5 : total / weight;
  return {
    bias: score >= 0.55 ? "Bullish" : score <= 0.45 ? "Bearish" : "Neutral",
    confidence: score,
  };
}

/** Tone helper so cards and headers colour consistently. */
export function biasToneOf(bias: Bias): "bull" | "bear" | "flat" {
  return bias === "Bullish" ? "bull" : bias === "Bearish" ? "bear" : "flat";
}

/** Tone for an explicit trade signal. */
export function recommendationTone(
  recommendation: Recommendation | null,
): "bull" | "bear" | "flat" {
  return recommendation === "BUY" ? "bull" : recommendation === "SELL" ? "bear" : "flat";
}

/**
 * Overall trade signal across the Decision Maker records in a set.
 *
 * Returns the most recent non-WAIT call, so the feed header shows the active
 * recommendation rather than being diluted by older WAIT cycles. Falls back to
 * `WAIT` when there is no directional call at all.
 */
export function latestRecommendation(
  insights: AnalysisInsight[],
): { recommendation: Recommendation; insight: AnalysisInsight | null } {
  const calls = insights.filter(
    (insight): insight is AnalysisInsight & { recommendation: Recommendation } =>
      insight.recommendation !== null,
  );
  if (!calls.length) return { recommendation: "WAIT", insight: null };
  const directional = calls.filter((insight) => insight.recommendation !== "WAIT");
  const pool = directional.length ? directional : calls;
  const newest = pool.reduce((best, insight) =>
    new Date(insight.timestamp).getTime() > new Date(best.timestamp).getTime()
      ? insight
      : best,
  );
  return { recommendation: newest.recommendation, insight: newest };
}

/** Direction of the record, for chart colouring (delegates to the shared tone). */
export function recordTone(record: SignalRecord) {
  return directionTone(record.direction);
}
