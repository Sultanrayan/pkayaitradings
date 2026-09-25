import type { ChartTimeframe, OhlcBar, OhlcSeries } from "@/lib/types";

/** Aggregate daily bars into weekly or monthly candles (client-side). */
export function aggregateOhlc(
  series: OhlcSeries,
  timeframe: Extract<ChartTimeframe, "W1" | "MN">,
): OhlcSeries {
  if (!series.bars.length) return series;

  const buckets = new Map<string, OhlcBar[]>();
  for (const bar of series.bars) {
    const date = new Date(bar.openTime);
    const key =
      timeframe === "W1"
        ? weekKey(date)
        : `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
    const bucket = buckets.get(key);
    if (bucket) bucket.push(bar);
    else buckets.set(key, [bar]);
  }

  const bars: OhlcBar[] = [];
  for (const group of buckets.values()) {
    const first = group[0];
    const last = group[group.length - 1];
    const high = Math.max(...group.map((bar) => bar.high));
    const low = Math.min(...group.map((bar) => bar.low));
    bars.push({
      openTime: first.openTime,
      open: first.open,
      high,
      low,
      close: last.close,
      volume: group.reduce((sum, bar) => sum + bar.volume, 0),
      tickVolume: group.reduce((sum, bar) => sum + bar.tickVolume, 0),
      isOpen: false,
      range: high - low,
    });
  }

  bars.sort((a, b) => new Date(a.openTime).getTime() - new Date(b.openTime).getTime());
  return { symbol: series.symbol, interval: timeframe, bars };
}

/** ISO-style week key (Monday-first), derived from UTC components. */
function weekKey(date: Date): string {
  const utc = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  const day = utc.getUTCDay() || 7;
  utc.setUTCDate(utc.getUTCDate() - day + 1);
  const year = utc.getUTCFullYear();
  const week = Math.ceil(
    ((utc.getTime() - new Date(Date.UTC(year, 0, 1)).getTime()) / 86_400_000 +
      new Date(Date.UTC(year, 0, 1)).getUTCDay() +
      1 -
      1) /
      7,
  );
  return `${year}-W${String(week).padStart(2, "0")}`;
}

/** OHLC limit that produces a reasonable number of candles for the timeframe. */
export function timeframeLimit(timeframe: ChartTimeframe): number {
  if (timeframe === "W1" || timeframe === "MN") return 1000; // aggr. from D1
  if (timeframe === "D1") return 500;
  if (timeframe === "H4" || timeframe === "H1") return 400;
  return 300;
}