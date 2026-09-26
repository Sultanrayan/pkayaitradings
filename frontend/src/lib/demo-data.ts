/**
 * Demo market data for viewing the UI without a live backend.
 *
 * Generates deterministic candle series, moving ticks and technical signal
 * markers from a simple seeded random walk. Activated with `?demo=1` or when
 * `NEXT_PUBLIC_DEMO_MODE=true`. Visual-only: numbers are synthetic, not real
 * market data.
 */

import type { ChartTimeframe, OhlcBar, SignalRecord, Tick, Timeframe } from "@/lib/types";

export interface DemoAsset {
  symbol: string;
  description: string;
  base: number; // starting price
  vol: number; // per-bar volatility
}

export const DEMO_ASSETS: DemoAsset[] = [
  { symbol: "XAUUSD", description: "Gold / US Dollar", base: 4270, vol: 0.0016 },
  { symbol: "BTCUSD", description: "Bitcoin / US Dollar", base: 96400, vol: 0.0032 },
  { symbol: "EURUSD", description: "Euro / US Dollar", base: 1.0845, vol: 0.0008 },
  { symbol: "US500", description: "US 500 Index", base: 6120, vol: 0.0011 },
];

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hashSeed(text: string): number {
  let hash = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function normal(rand: () => number): number {
  // Box–Muller for a roughly normal step.
  const u = Math.max(rand(), 1e-9);
  const v = Math.max(rand(), 1e-9);
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

export const TIMEFRAME_SECONDS: Record<ChartTimeframe, number> = {
  M1: 60,
  M5: 300,
  M15: 900,
  M30: 1800,
  H1: 3600,
  H4: 14400,
  D1: 86400,
  W1: 604800,
  MN: 2592000,
};

export function demoAsset(symbol: string): DemoAsset {
  return DEMO_ASSETS.find((item) => item.symbol === symbol) ?? DEMO_ASSETS[0];
}

export function demoAssetSymbols(): string[] {
  return DEMO_ASSETS.map((item) => item.symbol);
}

/**
 * Generate `count` candles ending "now", oldest first. Streaming updates the
 * latest (in-progress) bar.
 */
export function generateDemoCandles(
  symbol: string,
  timeframe: ChartTimeframe,
  count = 300,
): OhlcBar[] {
  const asset = demoAsset(symbol);
  const rand = mulberry32(hashSeed(`${symbol}:${timeframe}:${count}`));
  const seconds = TIMEFRAME_SECONDS[timeframe];
  const now = Date.now();
  const stepVol = asset.vol * Math.sqrt(Math.max(seconds / 3600, 0.05));
  const bars: OhlcBar[] = [];
  let price = asset.base * (0.96 + rand() * 0.08);

  for (let i = count - 1; i >= 0; i -= 1) {
    const openTimeMs = now - i * seconds;
    const openTime = new Date(openTimeMs).toISOString();
    const drift = 0.02 + rand() * 0.12; // slight trend bias per bar
    const move = normal(rand) * stepVol * drift;
    const close = Math.max(price * (1 + move), asset.base * 0.2);
    const wick = stepVol * (0.4 + rand() * 0.6);
    const spreadHigh = Math.max(price, close) * (1 + wick);
    const spreadLow = Math.min(price, close) * (1 - wick);
    const high = Math.round(Math.max(spreadHigh, asset.base * 0.2) * 100) / 100;
    const low = Math.round(Math.max(spreadLow, asset.base * 0.15) * 100) / 100;
    const baseVol = 40 + rand() * 120;
    const volume = Math.round(baseVol * (1 + Math.abs(move) * 40));
    const isOpen = i === 0;
    bars.push({
      openTime,
      open: Number(price.toFixed(2)),
      high: Number(high.toFixed(2)),
      low: Number(Math.max(low, asset.base * 0.15).toFixed(2)),
      close: Number(close.toFixed(2)),
      volume: Number(volume.toFixed(2)),
      tickVolume: Math.round(volume * (1 + rand())),
      isOpen,
      range: Number((high - low).toFixed(2)),
    });
    price = close;
  }
  return bars;
}

/** Lightweight live simulation: a Tick for an asset at a given timestamp. */
export function generateDemoTick(symbol: string, at: number = Date.now()): Tick {
  const asset = demoAsset(symbol);
  const secondary = Math.sin(at / 5500) * asset.base * 0.0004;
  const noise = Math.sin(at / 1370) * asset.base * 0.0002;
  const mid = asset.base + secondary + noise;
  const open = asset.base * 0.995;
  const change = ((mid - open) / open) * 100;
  return {
    symbol,
    description: asset.description,
    bid: Number((mid - asset.base * 0.0001).toFixed(4)),
    ask: Number((mid + asset.base * 0.0001).toFixed(4)),
    mid: Number(mid.toFixed(4)),
    spread: Number((asset.base * 0.0002).toFixed(4)),
    high: Number((mid + asset.base * 0.002).toFixed(4)),
    low: Number((mid - asset.base * 0.002).toFixed(4)),
    direction: change >= 0 ? "UP" : "DOWN",
    dayDiffPercent: Number(change.toFixed(3)),
    timestamp: new Date(at).toISOString(),
    source: "demo",
    marketState: "open",
    stale: false,
    quoteAgeSeconds: 0,
    lastQuoteAt: new Date(at).toISOString(),
    is_tradeable: true,
  };
}

/** Deterministic technical signals to populate chart markers. */
export function generateDemoSignals(symbol: string, timeframe: ChartTimeframe, count = 60): SignalRecord[] {
  const asset = demoAsset(symbol);
  const rand = mulberry32(hashSeed(`signals:${symbol}:${timeframe}`));
  const seconds = TIMEFRAME_SECONDS[timeframe];
  const now = Date.now();
  const records: SignalRecord[] = [];
  for (let i = 0; i < count; i += 1) {
    const bullish = rand() > 0.5;
    const confidence = 0.5 + rand() * 0.45;
    const ts = now - i * seconds * (2 + Math.floor(rand() * 4));
    records.push({
      id: `demo-${symbol}-${timeframe}-${i}`,
      correlation_id: `demo-cycle-${i}`,
      symbol,
      agent: "technical_analyst",
      kind: "technical_signal",
      direction: bullish ? "BULLISH" : "BEARISH",
      confidence: Number(confidence.toFixed(3)),
      created_at: new Date(ts).toISOString(),
      payload: {
        signal: bullish ? "BULLISH" : "BEARISH",
        key_levels: {
          support: Number((asset.base * (1 - 0.01 - rand() * 0.01)).toFixed(2)),
          resistance: Number((asset.base * (1 + 0.01 + rand() * 0.01)).toFixed(2)),
        },
        reasoning: bullish
          ? "Momentum and trend filters align on the demo feed."
          : "Momentum is fading and the demo regression filter flashed a warning.",
      },
    });
  }
  return records;
}

/** Resolve the underlying backend interval string for an aggregate timeframe. */
export function demoSourceInterval(timeframe: ChartTimeframe): Timeframe {
  if (timeframe === "W1" || timeframe === "MN") return "D1";
  return timeframe;
}