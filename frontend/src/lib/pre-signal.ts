/**
 * Pre-Signal System — detection engine.
 *
 * Implements the design in `Research/indicator-graph.md`: instead of waiting for
 * a confirmed signal, warn as price *approaches* the psychological reference
 * levels, escalating through four severity levels.
 *
 * | Level | Name     | Meaning                          |
 * |-------|----------|----------------------------------|
 * | 1     | WATCH    | far from the zone                |
 * | 2     | PREPARE  | approaching the zone             |
 * | 3     | READY    | inside the zone                  |
 * | 4     | ACTION   | zone crossed / level confirmed   |
 *
 * Both reference levels are derived from real candles:
 *   • OP — Opening Price, the open of the current UTC session
 *   • BE — Break Even, the session's volume-weighted average price (the point
 *          at which the session's participants are flat, so reactions are sharp)
 *
 * Everything is computed locally from the OHLC series already fetched by the
 * app, so this introduces no new endpoint and no synthetic data.
 */

import { atr, macd as macdSeries, rsi as rsiSeries } from "@/lib/indicators";

export type PreSignalLevel = 0 | 1 | 2 | 3 | 4;

export type PreSignalDirection = "bullish" | "bearish" | "neutral";

export interface PreSignalZone {
  key: "be" | "op";
  label: string;
  price: number;
}

export interface PreSignalState {
  /** False until enough candles are available to classify. */
  ready: boolean;
  level: PreSignalLevel;
  levelName: string;
  /** The zone price is currently closest to. */
  nearest: PreSignalZone | null;
  /** All reference levels, ordered by distance from the last close. */
  zones: PreSignalZone[];
  lastClose: number | null;
  /** Signed distance to the nearest zone, as a fraction of price. */
  proximityPercent: number;
  direction: PreSignalDirection;
  /** True when price has crossed the nearest zone (level 4). */
  crossed: boolean;
  /** The four false-signal filters from the research doc. */
  filters: {
    confirmation: boolean;
    timeframe: boolean;
    context: boolean;
    time: boolean;
  };
  /** Filters passed / total. */
  confirmationScore: number;
  /** Volatility state used by the "calm before the storm" heuristic. */
  volatilitySpike: boolean;
  volatilitySqueeze: boolean;
  atrPercent: number | null;
}

const LEVEL_NAMES: Record<PreSignalLevel, string> = {
  0: "NO ZONE",
  1: "WATCH",
  2: "PREPARE",
  3: "READY",
  4: "ACTION",
};

/**
 * Severity banding, expressed as a fraction of ATR so the thresholds adapt to
 * gold, FX and crypto instead of using fixed percentages.
 */
const WATCH_ATR = 3.0;
const PREPARE_ATR = 2.0;
const READY_ATR = 1.0;

/** Start of the UTC trading day, used to find the session open. */
function sessionOpenMs(ms: number): number {
  const date = new Date(ms);
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
}

function isSameUtcDay(a: number, b: number): boolean {
  return sessionOpenMs(a) === sessionOpenMs(b);
}

/**
 * Classify the current pre-signal state from a candle series.
 *
 * @param bars Oldest-first OHLC candles.
 * @param trendBias Higher-timeframe bias when known; used by the timeframe filter.
 */
export function detectPreSignal(
  bars: Array<{ openTime: string; open: number; high: number; low: number; close: number; volume: number }>,
  trendBias?: "Bullish" | "Bearish" | "Neutral",
): PreSignalState {
  const empty: PreSignalState = {
    ready: false,
    level: 0,
    levelName: LEVEL_NAMES[0],
    nearest: null,
    zones: [],
    lastClose: null,
    proximityPercent: 0,
    direction: "neutral",
    crossed: false,
    filters: { confirmation: false, timeframe: false, context: false, time: false },
    confirmationScore: 0,
    volatilitySpike: false,
    volatilitySqueeze: false,
    atrPercent: null,
  };

  if (bars.length < 30) return empty;

  const closes = bars.map((bar) => bar.close);
  const last = bars[bars.length - 1];
  const lastClose = last.close;

  // --- Reference levels -------------------------------------------------
  // Session window: bars sharing the last candle's UTC day.
  const lastMs = new Date(last.openTime).getTime();
  const session = bars.filter((bar) => isSameUtcDay(new Date(bar.openTime).getTime(), lastMs));
  const openingPrice = session.length ? session[0].open : bars[0].open;

  // Break-even reference = session VWAP over the current session.
  let cumulativeTypicalVolume = 0;
  let cumulativeTypicalPriceVolume = 0;
  for (const bar of session) {
    const typical = (bar.high + bar.low + bar.close) / 3;
    cumulativeTypicalVolume += bar.volume;
    cumulativeTypicalPriceVolume += typical * bar.volume;
  }
  const vwap =
    cumulativeTypicalVolume > 0
      ? cumulativeTypicalPriceVolume / cumulativeTypicalVolume
      : openingPrice;

  const zones: PreSignalZone[] = ([
    { key: "be", label: "BE", price: vwap },
    { key: "op", label: "OP", price: openingPrice },
  ] as PreSignalZone[]).sort(
    (a, b) => Math.abs(b.price - lastClose) - Math.abs(a.price - lastClose),
  );

  // --- Volatility -------------------------------------------------------
  const atrValues = atr(
    bars.map((bar) => ({
      openTime: bar.openTime,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
      volume: bar.volume,
      tickVolume: 0,
      isOpen: false,
      range: bar.high - bar.low,
    })),
    14,
  );
  const atrLast = [...atrValues].reverse().find((value) => value !== null) ?? null;
  const atrPercent = atrLast !== null && lastClose ? (atrLast / lastClose) * 100 : null;

  // Volatility spike / squeeze against the recent ATR baseline.
  const atrHistory = atrValues.filter((value): value is number => value !== null).slice(-60);
  const atrMean =
    atrHistory.length > 0 ? atrHistory.reduce((sum, value) => sum + value, 0) / atrHistory.length : null;
  const volatilitySpike = atrLast !== null && atrMean !== null && atrMean > 0 && atrLast > atrMean * 1.4;
  const volatilitySqueeze =
    atrLast !== null && atrMean !== null && atrMean > 0 && atrLast < atrMean * 0.7;

  // --- Proximity & severity --------------------------------------------
  const nearest = zones[0] ?? null;
  const distance = nearest ? Math.abs(lastClose - nearest.price) : 0;
  const inAtr = atrLast && atrLast > 0 ? distance / atrLast : Number.POSITIVE_INFINITY;

  let level: PreSignalLevel = 0;
  if (nearest) {
    if (inAtr <= READY_ATR) level = 3;
    else if (inAtr <= PREPARE_ATR) level = 2;
    else if (inAtr <= WATCH_ATR) level = 1;
  }

  const crossed = nearest ? lastClose >= nearest.price : false;
  if (level >= 3 && crossed) level = 4;

  // Direction of the approach: above the zone is bullish (per the research
  // doc's "above = bullish, below = bearish" rule).
  let direction: PreSignalDirection = "neutral";
  if (nearest) {
    const delta = lastClose - nearest.price;
    if (Math.abs(delta) < (atrLast ?? 0) * 0.25) direction = "neutral";
    else direction = delta > 0 ? "bullish" : "bearish";
  }

  // --- False-signal filters --------------------------------------------
  const rsiValues = rsiSeries(closes, 14);
  const rsiLast = [...rsiValues].reverse().find((value) => value !== null) ?? null;
  const histogramLast = [...macdSeries(closes, 12, 26, 9).histogram]
    .reverse()
    .find((value) => value !== null) ?? null;
  const previousClose = bars[bars.length - 2]?.close ?? lastClose;
  const bodyMove = Math.abs(lastClose - previousClose);

  // 1. Confirmation — momentum and RSI must agree with the approach.
  const momentumAgrees =
    direction === "neutral" ||
    (direction === "bullish"
      ? (histogramLast ?? 0) >= 0
      : (histogramLast ?? 0) <= 0);
  const rsiAgrees =
    rsiLast === null ||
    (direction === "bullish" ? rsiLast >= 45 : rsiLast <= 55);
  const confirmation = momentumAgrees && rsiAgrees;

  // 2. Timeframe alignment with the higher-timeframe bias.
  const timeframe =
    trendBias === undefined ||
    trendBias === "Neutral" ||
    direction === "neutral" ||
    (direction === "bullish" && trendBias === "Bullish") ||
    (direction === "bearish" && trendBias === "Bearish");

  // 3. Context — a squeeze or spike means the move is still developing;
  //    a dead-flat tape does not.
  const context = volatilitySpike || volatilitySqueeze || direction === "neutral";

  // 4. Time — require a real candle body, not a wick graze.
  const time = atrLast !== null ? bodyMove >= atrLast * 0.15 : false;

  const filters = { confirmation, timeframe, context, time };
  const confirmationScore =
    (Number(confirmation) + Number(timeframe) + Number(context) + Number(time)) / 4;

  return {
    ready: true,
    level,
    levelName: LEVEL_NAMES[level],
    nearest,
    zones,
    lastClose,
    proximityPercent: lastClose ? (distance / lastClose) * 100 : 0,
    direction,
    crossed,
    filters,
    confirmationScore,
    volatilitySpike,
    volatilitySqueeze,
    atrPercent,
  };
}

/** Colour per severity level — the traffic-light model from the research doc. */
export const LEVEL_COLOR: Record<PreSignalLevel, string> = {
  0: "#71717a",
  1: "#eab308", // yellow — watch
  2: "#f97316", // orange — prepare
  3: "#ef4444", // red — ready
  4: "#22c55e", // green — action
};

export const LEVEL_TONE_CLASS: Record<PreSignalLevel, string> = {
  0: "bg-muted text-muted-foreground ring-border",
  1: "bg-gold/10 text-gold ring-gold/30",
  2: "bg-[#f97316]/10 text-[#f97316] ring-[#f97316]/30",
  3: "bg-bear/10 text-bear ring-bear/30",
  4: "bg-bull/10 text-bull ring-bull/30",
};

export const PRE_SIGNAL_LEVELS: Array<{ level: PreSignalLevel; name: string; action: string }> = [
  { level: 1, name: "Watch", action: "Price far from the zone" },
  { level: 2, name: "Prepare", action: "Approaching the zone" },
  { level: 3, name: "Ready", action: "Inside the zone" },
  { level: 4, name: "Action", action: "Zone crossed" },
];
