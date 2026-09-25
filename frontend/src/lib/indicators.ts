import type { OhlcBar } from "@/lib/types";

/** Client-side technical indicators used for chart overlays. */

export type Nullable = number | null;

export function sma(values: number[], period: number): Nullable[] {
  const out: Nullable[] = new Array(values.length).fill(null);
  if (period <= 0) return out;
  let sum = 0;
  for (let i = 0; i < values.length; i += 1) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

export function ema(values: number[], period: number): Nullable[] {
  const out: Nullable[] = new Array(values.length).fill(null);
  if (period <= 0 || values.length < period) return out;
  const k = 2 / (period + 1);
  let previous = 0;
  for (let i = 0; i < values.length; i += 1) {
    if (i < period - 1) {
      previous += values[i];
      continue;
    }
    if (i === period - 1) {
      previous = (previous + values[i]) / period;
      out[i] = previous;
      continue;
    }
    previous = values[i] * k + previous * (1 - k);
    out[i] = previous;
  }
  return out;
}

export function rsi(values: number[], period = 14): Nullable[] {
  const out: Nullable[] = new Array(values.length).fill(null);
  if (values.length <= period) return out;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i += 1) {
    const change = values[i] - values[i - 1];
    if (change >= 0) gain += change;
    else loss -= change;
  }
  let avgGain = gain / period;
  let avgLoss = loss / period;
  out[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  for (let i = period + 1; i < values.length; i += 1) {
    const change = values[i] - values[i - 1];
    const up = change > 0 ? change : 0;
    const down = change < 0 ? -change : 0;
    avgGain = (avgGain * (period - 1) + up) / period;
    avgLoss = (avgLoss * (period - 1) + down) / period;
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }
  return out;
}

export function macd(
  values: number[],
  fast = 12,
  slow = 26,
  signalPeriod = 9,
): { macd: Nullable[]; signal: Nullable[]; histogram: Nullable[] } {
  const fastEma = ema(values, fast);
  const slowEma = ema(values, slow);
  const macdLine: Nullable[] = values.map((_, i) =>
    fastEma[i] !== null && slowEma[i] !== null ? (fastEma[i] as number) - (slowEma[i] as number) : null,
  );
  const compact = macdLine.filter((value): value is number => value !== null);
  const signalCompact = ema(compact, signalPeriod);
  const signalLine: Nullable[] = new Array(values.length).fill(null);
  let cursor = 0;
  for (let i = 0; i < macdLine.length; i += 1) {
    if (macdLine[i] !== null) {
      signalLine[i] = signalCompact[cursor] ?? null;
      cursor += 1;
    }
  }
  const histogram = macdLine.map((value, i) =>
    value !== null && signalLine[i] !== null ? value - (signalLine[i] as number) : null,
  );
  return { macd: macdLine, signal: signalLine, histogram };
}

export function bollinger(
  values: number[],
  period = 20,
  mult = 2,
): { upper: Nullable[]; middle: Nullable[]; lower: Nullable[] } {
  const middle = sma(values, period);
  const upper: Nullable[] = new Array(values.length).fill(null);
  const lower: Nullable[] = new Array(values.length).fill(null);
  for (let i = period - 1; i < values.length; i += 1) {
    const window = values.slice(i - period + 1, i + 1);
    const mean = middle[i] as number;
    const variance = window.reduce((acc, value) => acc + (value - mean) ** 2, 0) / period;
    const std = Math.sqrt(variance);
    upper[i] = mean + mult * std;
    lower[i] = mean - mult * std;
  }
  return { upper, middle, lower };
}

export function atr(bars: OhlcBar[], period = 14): Nullable[] {
  const out: Nullable[] = new Array(bars.length).fill(null);
  if (bars.length <= period) return out;
  const trueRanges: number[] = bars.map((bar, i) => {
    if (i === 0) return bar.high - bar.low;
    const previousClose = bars[i - 1].close;
    return Math.max(
      bar.high - bar.low,
      Math.abs(bar.high - previousClose),
      Math.abs(bar.low - previousClose),
    );
  });
  let sum = 0;
  for (let i = 0; i < period; i += 1) sum += trueRanges[i];
  let previous = sum / period;
  out[period - 1] = previous;
  for (let i = period; i < bars.length; i += 1) {
    previous = (previous * (period - 1) + trueRanges[i]) / period;
    out[i] = previous;
  }
  return out;
}

export function stochastic(
  bars: OhlcBar[],
  kPeriod = 14,
  dPeriod = 3,
): { k: Nullable[]; d: Nullable[] } {
  const k: Nullable[] = new Array(bars.length).fill(null);
  for (let i = kPeriod - 1; i < bars.length; i += 1) {
    const window = bars.slice(i - kPeriod + 1, i + 1);
    const highest = Math.max(...window.map((bar) => bar.high));
    const lowest = Math.min(...window.map((bar) => bar.low));
    const span = highest - lowest;
    k[i] = span === 0 ? 50 : ((bars[i].close - lowest) / span) * 100;
  }
  const compact = k.filter((value): value is number => value !== null);
  const dCompact = sma(compact, dPeriod);
  const d: Nullable[] = new Array(bars.length).fill(null);
  let cursor = 0;
  for (let i = 0; i < k.length; i += 1) {
    if (k[i] !== null) {
      d[i] = dCompact[cursor] ?? null;
      cursor += 1;
    }
  }
  return { k, d };
}

/** Simple period-over-period returns. */
export function returns(values: number[]): number[] {
  const out: number[] = [];
  for (let i = 1; i < values.length; i += 1) {
    const previous = values[i - 1];
    out.push(previous === 0 ? 0 : (values[i] - previous) / previous);
  }
  return out;
}

/** Pearson correlation of two equal-length series (0 when undefined). */
export function pearson(left: number[], right: number[]): number {
  const length = Math.min(left.length, right.length);
  if (length < 2) return 0;
  const a = left.slice(-length);
  const b = right.slice(-length);
  const meanA = a.reduce((sum, value) => sum + value, 0) / length;
  const meanB = b.reduce((sum, value) => sum + value, 0) / length;
  let covariance = 0;
  let varianceA = 0;
  let varianceB = 0;
  for (let i = 0; i < length; i += 1) {
    const da = a[i] - meanA;
    const db = b[i] - meanB;
    covariance += da * db;
    varianceA += da * da;
    varianceB += db * db;
  }
  const denominator = Math.sqrt(varianceA * varianceB);
  return denominator === 0 ? 0 : covariance / denominator;
}

/** Simple moving average of a nullable series (for indicator smoothing). */
export function smaNullable(values: Nullable[], period: number): Nullable[] {
  const out: Nullable[] = new Array(values.length).fill(null);
  for (let i = period - 1; i < values.length; i += 1) {
    let sum = 0;
    let count = 0;
    for (let j = i - period + 1; j <= i; j += 1) {
      const value = values[j];
      if (value !== null) {
        sum += value;
        count += 1;
      }
    }
    if (count === period) out[i] = sum / period;
  }
  return out;
}
