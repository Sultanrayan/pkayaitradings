/**
 * Market intelligence derivation.
 *
 * Pure functions that turn raw candles (+ the latest signals) into the
 * analytical metrics the dashboard presents: market structure, trend,
 * momentum, volatility, volume, technical states, key levels and a
 * confidence breakdown.
 *
 * Everything here is descriptive — it describes what the data shows and never
 * produces an execution instruction.
 */

import { atr, ema, macd as macdSeries, rsi as rsiSeries } from "@/lib/indicators";
import { directionTone, type Tone } from "@/lib/format";
import type { OhlcBar, SignalRecord } from "@/lib/types";

export type Bias = "Bullish" | "Bearish" | "Neutral";
export type Strength = "Strong" | "Moderate" | "Weak";
export type Level = "Low" | "Medium" | "High";

export interface TechnicalRow {
  label: string;
  value: string;
  state: Bias | Level | string;
  tone: Tone;
}

export interface ConfidencePart {
  label: string;
  /** 0..1 */
  value: number;
  /** True when no sentiment signal was available for this factor. */
  pending?: boolean;
}

export interface KeyLevel {
  label: string;
  price: number;
  tone: Tone;
}

export interface MarketIntel {
  ready: boolean;
  price: number | null;
  rsi: number | null;
  ema20: number | null;
  ema50: number | null;
  ema200: number | null;
  macdHistogram: number | null;
  volumeChangePercent: number | null;
  /** Market structure — the dashboard's headline bias. */
  structure: Bias;
  structureNote: string;
  trend: Bias;
  momentum: Strength;
  volatility: Level;
  volume: Level;
  /** 0..1 composite confidence in the structural read. */
  score: number;
  reasons: string[];
  technical: TechnicalRow[];
  breakdown: ConfidencePart[];
  levels: KeyLevel[];
}

const clamp01 = (value: number): number => Math.min(1, Math.max(0, value));

function lastValue(values: (number | null)[]): number | null {
  for (let i = values.length - 1; i >= 0; i -= 1) {
    const value = values[i];
    if (value !== null && Number.isFinite(value)) return value;
  }
  return null;
}

function mean(values: number[]): number | null {
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function median(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

/** Adaptive buckets keep thresholds meaningful across gold, FX and crypto. */
function bucket(value: number, low: number, high: number): Level {
  if (value < low) return "Low";
  if (value > high) return "High";
  return "Medium";
}

function biasTone(bias: Bias): Tone {
  if (bias === "Bullish") return "bull";
  if (bias === "Bearish") return "bear";
  return "flat";
}

function levelTone(level: Level): Tone {
  if (level === "High") return "bull";
  if (level === "Low") return "bear";
  return "flat";
}

/** Latest sentiment reading from news signals, if the feed has any. */
function sentimentScore(signals: SignalRecord[]): number | null {
  const news = signals.filter((record) => record.kind === "news_signal");
  if (!news.length) return null;
  const total = news.reduce((sum, record) => {
    const sentiment = String(
      (record.payload as { sentiment?: string } | undefined)?.sentiment ?? record.direction,
    ).toUpperCase();
    const mapped =
      sentiment.includes("VERY_BULL") || sentiment === "BULLISH"
        ? 1
        : sentiment.includes("VERY_BEAR") || sentiment === "BEARISH"
          ? 0
          : 0.5;
    return sum + mapped * clamp01(record.confidence);
  }, 0);
  return clamp01(total / news.length);
}

/** Nearest sentiment reading → used for the MARKET STRUCTURE sub-label. */
function sentimentNote(signals: SignalRecord[]): string | null {
  const news = signals.filter((record) => record.kind === "news_signal");
  if (!news.length) return null;
  const sentiment = String(
    (news[0].payload as { sentiment?: string } | undefined)?.sentiment ?? "",
  )
    .replace(/_/g, " ")
    .toLowerCase();
  return sentiment ? `Sentiment ${sentiment}` : null;
}

export function deriveMarketIntel(
  bars: OhlcBar[],
  signals: SignalRecord[],
  latestSignal: SignalRecord | null,
): MarketIntel {
  const closes = bars.map((bar) => bar.close);
  const price = closes.length ? closes[closes.length - 1] : null;

  const ema20Series = ema(closes, 20);
  const ema50Series = ema(closes, 50);
  const ema200Series = ema(closes, 200);
  const rsiValues = rsiSeries(closes, 14);
  const macdValues = macdSeries(closes, 12, 26, 9);
  const atrValues = atr(bars, 14);

  const ema20 = lastValue(ema20Series);
  const ema50 = lastValue(ema50Series);
  const ema200 = lastValue(ema200Series);
  const rsi = lastValue(rsiValues);
  const macdHistogram = lastValue(macdValues.histogram);
  const atrValue = lastValue(atrValues);
  const macdLine = lastValue(macdValues.macd);
  const macdSignal = lastValue(macdValues.signal);

  // Trend: position relative to the moving averages plus their slope.
  let trendScore = 0;
  if (price !== null && ema50 !== null) trendScore += price > ema50 ? 0.35 : -0.35;
  if (price !== null && ema20 !== null) trendScore += price > ema20 ? 0.25 : -0.25;
  if (ema20 !== null && ema50 !== null) trendScore += ema20 > ema50 ? 0.2 : -0.2;
  if (price !== null && ema200 !== null) trendScore += price > ema200 ? 0.2 : -0.2;

  const previousEma50 = ema50Series.length > 6 ? ema50Series[ema50Series.length - 6] : null;
  if (ema50 !== null && previousEma50 !== null) {
    trendScore += ema50 > previousEma50 ? 0.1 : -0.1;
  }

  const trend: Bias = trendScore > 0.2 ? "Bullish" : trendScore < -0.2 ? "Bearish" : "Neutral";

  // Momentum: RSI distance from 50 combined with MACD histogram strength.
  const macdStrength = macdHistogram === null || price === null ? 0 : (macdHistogram / price) * 400;
  let momentumStrength = 0;
  if (rsi !== null) momentumStrength += (rsi - 50) / 25;
  momentumStrength += Math.max(-1.5, Math.min(1.5, macdStrength));
  const momentum: Strength =
    Math.abs(momentumStrength) >= 1.4 ? "Strong" : Math.abs(momentumStrength) >= 0.6 ? "Moderate" : "Weak";

  // Volatility: ATR as a share of price, compared with its own recent median.
  const atrPctSeries = bars
    .map((_, index) => {
      const value = atrValues[index];
      const close = bars[index]?.close;
      return value !== null && close ? (value / close) * 100 : null;
    })
    .filter((value): value is number => value !== null);
  const atrPct = atrValue !== null && price ? (atrValue / price) * 100 : null;
  const atrPctMedian = median(atrPctSeries.slice(-120));
  const volatility: Level =
    atrPct === null || atrPctMedian === null || atrPctMedian === 0
      ? "Medium"
      : bucket(atrPct / atrPctMedian, 0.7, 1.4);

  // Volume: latest bar against the mean of the preceding window.
  const volumes = bars.map((bar) => bar.volume).filter((value) => Number.isFinite(value));
  const baseline = mean(volumes.slice(-21, -1));
  const latestVolume = volumes.length ? volumes[volumes.length - 1] : null;
  const volumeRatio =
    baseline && latestVolume !== null && baseline !== 0 ? latestVolume / baseline : null;
  const volume: Level = volumeRatio === null ? "Medium" : bucket(volumeRatio, 0.8, 1.25);
  const volumeChangePercent =
    volumeRatio === null ? null : Math.round((volumeRatio - 1) * 1000) / 10;

  // Technical score: blend trend, RSI position and MACD agreement.
  const rsiComponent = rsi === null ? 0.5 : clamp01((rsi - 30) / 40);
  const macdComponent =
    macdLine === null || macdSignal === null ? 0.5 : clamp01(0.5 + (macdLine - macdSignal) * 0.5);
  const technicalScore = clamp01(
    clamp01(0.5 + trendScore / 2) * 0.55 + rsiComponent * 0.25 + macdComponent * 0.2,
  );

  const momentumScore = clamp01(0.5 + momentumStrength / 3);
  const volumeScore = clamp01(0.5 + (volumeRatio === null ? 0 : volumeRatio - 1) / 2);
  const sentiment = sentimentScore(signals);

  const parts: ConfidencePart[] = [
    { label: "Technical analysis", value: technicalScore },
    { label: "Momentum", value: momentumScore },
    { label: "Volume", value: volumeScore },
    sentiment === null
      ? { label: "Market sentiment", value: 0.5, pending: true }
      : { label: "Market sentiment", value: sentiment },
  ];

  const weighted = parts.reduce((sum, part) => sum + part.value, 0) / parts.length;
  const score = clamp01(weighted);
  const structure: Bias = score >= 0.55 ? "Bullish" : score <= 0.45 ? "Bearish" : "Neutral";

  // WHY — every bullet is derived from a computed value, never invented.
  const reasons: string[] = [];
  if (price !== null && ema20 !== null && ema50 !== null) {
    const above = price > ema20 && price > ema50;
    reasons.push(
      `Price is ${above ? "above" : "below"} the EMA 20 and EMA 50 structure`,
    );
  }
  if (rsi !== null) {
    const zone = rsi >= 70 ? "overbought" : rsi <= 30 ? "oversold" : rsi >= 55 ? "firm" : rsi <= 45 ? "weakening" : "neutral";
    reasons.push(`RSI at ${rsi.toFixed(0)} is ${zone}`);
  }
  if (macdHistogram !== null) {
    reasons.push(`MACD momentum is ${macdHistogram >= 0 ? "positive" : "negative"}`);
  }
  if (volumeChangePercent !== null) {
    const word = volumeChangePercent >= 0 ? "rising" : "falling";
    reasons.push(`Volume is ${word} ${Math.abs(volumeChangePercent).toFixed(0)}% versus its average`);
  }

  // Technical readout rows.
  const technical: TechnicalRow[] = [];
  if (rsi !== null) {
    technical.push({
      label: "RSI (14)",
      value: rsi.toFixed(0),
      state: rsi >= 55 ? "Bullish" : rsi <= 45 ? "Bearish" : "Neutral",
      tone: biasTone(rsi >= 55 ? "Bullish" : rsi <= 45 ? "Bearish" : "Neutral"),
    });
  }
  if (macdLine !== null && macdSignal !== null) {
    const bullish = macdLine > macdSignal;
    technical.push({
      label: "MACD",
      value: bullish ? "Bullish" : "Bearish",
      state: bullish ? "Bullish" : "Bearish",
      tone: biasTone(bullish ? "Bullish" : "Bearish"),
    });
  }
  if (price !== null && ema20 !== null) {
    technical.push({
      label: "EMA 20",
      value: `${price > ema20 ? "Above" : "Below"} price`,
      state: price > ema20 ? "Bullish" : "Bearish",
      tone: biasTone(price > ema20 ? "Bullish" : "Bearish"),
    });
  }
  if (price !== null && ema50 !== null) {
    technical.push({
      label: "EMA 50",
      value: `${price > ema50 ? "Above" : "Below"} price`,
      state: price > ema50 ? "Bullish" : "Bearish",
      tone: biasTone(price > ema50 ? "Bullish" : "Bearish"),
    });
  }
  if (volumeChangePercent !== null) {
    technical.push({
      label: "Volume",
      value: `${volumeChangePercent >= 0 ? "+" : ""}${volumeChangePercent.toFixed(0)}%`,
      state: volume,
      tone: levelTone(volume),
    });
  }
  if (atrPct !== null) {
    technical.push({
      label: "ATR (14)",
      value: `${atrPct.toFixed(2)}%`,
      state: volatility,
      tone: levelTone(volatility),
    });
  }

  // Key levels: signal levels when available, otherwise recent swing extremes.
  const payload = (latestSignal?.payload ?? {}) as {
    key_levels?: { support?: number | null; resistance?: number | null };
  };
  const recentHigh = bars.length ? Math.max(...bars.slice(-60).map((bar) => bar.high)) : null;
  const recentLow = bars.length ? Math.min(...bars.slice(-60).map((bar) => bar.low)) : null;
  const resistance = payload.key_levels?.resistance ?? recentHigh;
  const support = payload.key_levels?.support ?? recentLow;

  const levels: KeyLevel[] = [];
  if (resistance !== null && resistance !== undefined) {
    levels.push({ label: "Resistance", price: resistance, tone: "bear" });
  }
  if (price !== null) {
    levels.push({ label: "Current price", price, tone: "flat" });
  }
  if (support !== null && support !== undefined) {
    levels.push({ label: "Support", price: support, tone: "bull" });
  }

  const note = sentimentNote(signals);
  const structureNote =
    note ?? `${momentum} momentum`;

  return {
    ready: bars.length > 0,
    price,
    rsi,
    ema20,
    ema50,
    ema200,
    macdHistogram,
    volumeChangePercent,
    structure,
    structureNote,
    trend,
    momentum,
    volatility,
    volume,
    score,
    reasons: reasons.slice(0, 4),
    technical,
    breakdown: parts,
    levels,
  };
}

/** Direction from a candle series only — used by the multi-timeframe row. */
export function biasFromBars(bars: OhlcBar[]): { bias: Bias; score: number } {
  if (bars.length < 30) return { bias: "Neutral", score: 0.5 };
  const closes = bars.map((bar) => bar.close);
  const price = closes[closes.length - 1];
  const ema20 = lastValue(ema(closes, 20));
  const ema50 = lastValue(ema(closes, 50));
  const rsi = lastValue(rsiSeries(closes, 14));
  const histogram = lastValue(macdSeries(closes, 12, 26, 9).histogram);

  let score = 0.5;
  if (ema20 !== null) score += price > ema20 ? 0.12 : -0.12;
  if (ema50 !== null) score += price > ema50 ? 0.14 : -0.14;
  if (rsi !== null) score += clamp01((rsi - 45) / 30) * 0.14 - 0.07;
  if (histogram !== null && price) score += Math.max(-0.1, Math.min(0.1, (histogram / price) * 30));

  const value = clamp01(score);
  return { bias: value >= 0.55 ? "Bullish" : value <= 0.45 ? "Bearish" : "Neutral", score: value };
}

/** Signal direction mapped to the dashboard's analytical vocabulary. */
export function signalBias(record: SignalRecord | null): Bias {
  if (!record) return "Neutral";
  const tone = directionTone(record.direction);
  if (tone === "bull") return "Bullish";
  if (tone === "bear") return "Bearish";
  return "Neutral";
}
