/**
 * Signal → card model: normalises a stored agent signal into the fields the
 * Signal card grid renders (Entry, SL, TP1, TP2, Confidence) plus a
 * deterministic sparkline/series for the charts.
 *
 * The wire records carry a single `take_profit` (from risk/decision payloads)
 * or key levels (technical signals); there is no explicit TP1/TP2, so the
 * first target is derived as the midpoint of the measured move and the second
 * as the full target. Series are seeded from the record id so a card and its
 * detail chart always agree.
 */

import type { SignalRecord } from "@/lib/types";

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

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export interface SignalLevels {
  entry: number | null;
  sl: number | null;
  tp1: number | null;
  tp2: number | null;
  confidence: number;
  /** True when a full entry/stops/target plan is present. */
  hasPlan: boolean;
}

const BULLISH = /BULL|UP|BUY/;
const BEARISH = /BEAR|DOWN|SELL/;

export function signalLevels(record: SignalRecord): SignalLevels {
  const payload = record.payload ?? {};
  const dir = (record.direction ?? "").toUpperCase();
  const bullish = BULLISH.test(dir);
  const bearish = BEARISH.test(dir);

  const key = (payload.key_levels ?? {}) as Record<string, unknown>;
  const support = asNumber(key.support);
  const resistance = asNumber(key.resistance);

  const entry = asNumber(payload.entry_price) ?? asNumber(payload.price);
  let sl = asNumber(payload.stop_loss);
  if (sl == null && (bullish || bearish)) {
    // Technical signals carry support / resistance instead of explicit stops.
    sl = bullish ? support : bearish ? resistance : null;
  }

  let tp2 = asNumber(payload.take_profit);
  if (tp2 == null) {
    tp2 = bullish ? resistance : bearish ? support : null;
  }
  if (tp2 == null && entry != null && sl != null) {
    const range = Math.abs(entry - sl);
    tp2 = entry + (bullish ? range * 2 : bearish ? -range * 2 : 0);
  }

  // When only the protective levels exist (e.g. risk records), approximate the
  // entry as their midpoint so the card plan and sparkline stay coherent.
  const derivedEntry =
    entry ??
    (sl != null && tp2 != null ? (sl + tp2) / 2 : null);

  // First target = midpoint of the measured move (the "partial close" level).
  const tp1 =
    tp2 != null && derivedEntry != null
      ? derivedEntry + (tp2 - derivedEntry) * 0.5
      : null;

  const confidence = asNumber(payload.final_score) ?? asNumber(payload.confidence) ?? record.confidence;
  const hasPlan = derivedEntry != null && sl != null && tp2 != null && (bullish || bearish);

  return { entry: derivedEntry, sl, tp1, tp2, confidence, hasPlan };
}

export function signalDirectionSign(record: SignalRecord): 1 | -1 | 0 {
  const dir = (record.direction ?? "").toUpperCase();
  if (BULLISH.test(dir)) return 1;
  if (BEARISH.test(dir)) return -1;
  return 0;
}

/**
 * A deterministic price path for a signal, seeded by its id. Starts slightly
 * off entry, dips toward the stop early (for directional plans), then walks to
 * the full target with a small wobble. Falls back to a gentle drift around
 * entry-price levels when no plan is present.
 */
export function signalSeriesValues(record: SignalRecord, count = 28): number[] {
  const levels = signalLevels(record);
  const entry = levels.entry ?? levels.tp2 ?? 100;
  const dist = levels.tp2 != null && entry != null ? levels.tp2 - entry : 0;
  const span = Math.abs(dist) || entry * 0.02;
  const rand = mulberry32(hashSeed(record.id));
  const phase = rand() * Math.PI * 2;
  const values: number[] = [];
  for (let i = 0; i < count; i += 1) {
    const progress = i / (count - 1);
    const base = entry + dist * progress;
    const wobble = Math.sin(progress * Math.PI * 3 + phase) * span * 0.06;
    const earlyDip =
      -Math.sign(dist) * span * 0.14 * Math.exp(-((progress - 0.28) ** 2) * 45);
    values.push(Number((base + wobble + earlyDip).toFixed(4)));
  }
  return values;
}

export interface SignalSeriesPoint {
  label: string;
  value: number;
}

/** Labeled series for the detail chart (every 5 "minutes" goes back in time). */
export function signalSeriesPoints(
  record: SignalRecord,
  count = 40,
): SignalSeriesPoint[] {
  const values = signalSeriesValues(record, count);
  return values.map((value, index) => ({
    label: index === values.length - 1 ? "Now" : `-${(values.length - 1 - index) * 5}m`,
    value,
  }));
}

/** Pick a sensible price precision from the largest level present. */
export function signalReference(record: SignalRecord): number {
  const levels = signalLevels(record);
  return levels.entry ?? levels.tp2 ?? levels.sl ?? 1;
}