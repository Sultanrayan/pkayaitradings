/**
 * TypeScript contract for the bar-anchored signal engine.
 *
 * Generated against the Python `Signal` dataclass (`signals/models.py`) and the
 * `to_dict()` serialisation it uses. The API returns `Signal.to_dict()` verbatim,
 * so these types describe the response exactly — there is no server-side
 * transformation between what the engine computed and what the chart receives.
 *
 * Matching rule, and why it matters: `timestamp` is the CLOSE time of the bar the
 * signal is anchored to, and `price` is that same bar's `close`. To plot a signal
 * on the correct candle, look up the bar by timestamp and place the marker at
 * `price`. Do not use `entry`/`sl`/`tp*` for the marker position, and do not shift
 * by a bar.
 */

/** Directional action. There is no WAIT: absence of a signal means `null`. */
export type SignalAction = "BUY" | "SELL";

/** The six confirmation layers, in reporting order. */
export type SignalLayerName =
  | "trend"
  | "momentum"
  | "volume"
  | "price_action"
  | "volatility"
  | "support_resistance";

/**
 * One directional signal anchored to a single confirmed, closed candle.
 *
 * Frozen server-side: a signal is never revised. If the market later disagrees,
 * a new signal appears (or none does); this object does not change.
 */
export interface TradeSignal {
  /** ISO-8601 UTC close time of the anchor bar. A key of the OHLCV index. */
  timestamp: string;
  /** Instrument ticker, upper-cased. */
  symbol: string;
  /** Candle interval, e.g. "H1". */
  timeframe: string;
  action: SignalAction;
  /** Close of the anchor bar. This is the value to plot the marker at. */
  price: number;
  /** Reference entry. Equal to `price` for a market entry on the bar close. */
  entry: number;
  /** Stop-loss level. Below entry for BUY, above for SELL. */
  sl: number;
  /** First take-profit. */
  tp1: number;
  /** Second take-profit, further out than `tp1`. */
  tp2: number;
  /** ATR on the anchor bar; the basis for all three levels. */
  atr: number;
  /** Weighted layer agreement in [0, 1]. */
  confidence: number;
  /** Human-readable justification naming the contributing layers. */
  reason: string;
  /** Per-layer directional score, each in [-1, 1]. */
  layers: Record<SignalLayerName, number>;
  /**
   * Identifies the configuration that produced this signal.
   *
   * Snake_case because the API serialises `Signal.to_dict()` verbatim and the
   * dataclass field is `strategy_version`. Converting it to camelCase here would
   * break the "API output matches the type exactly" property that makes the
   * contract checkable.
   */
  strategy_version: string;
}

/** Response of `GET /api/v1/signals/{symbol}/{timeframe}/history`. */
export interface SignalHistoryResponse {
  symbol: string;
  timeframe: string;
  count: number;
  /** Oldest first. */
  signals: TradeSignal[];
}

/** Response of `GET /api/v1/signals/{symbol}/{timeframe}/range`. */
export interface SignalRangeResponse extends SignalHistoryResponse {}

/** Error body shape used by the engine's endpoints. */
export interface SignalErrorResponse {
  detail: string;
}

/**
 * Fetch the most recent signal for a pair.
 *
 * Returns `null` on 404 — no signal yet is a normal state, not an error, so the
 * caller distinguishes "none" from "failed" via the boolean return.
 */
export async function fetchLatestSignal(
  symbol: string,
  timeframe: string,
  token?: string,
): Promise<TradeSignal | null> {
  const path = `/api/v1/signals/${encodeURIComponent(symbol)}/${encodeURIComponent(timeframe)}/latest`;
  const response = await fetch(path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`latest signal failed: ${response.status}`);
  }
  return (await response.json()) as TradeSignal;
}

/** Fetch recent signals for a pair, oldest first. */
export async function fetchSignalHistory(
  symbol: string,
  timeframe: string,
  limit = 100,
  token?: string,
): Promise<SignalHistoryResponse> {
  const path =
    `/api/v1/signals/${encodeURIComponent(symbol)}/${encodeURIComponent(timeframe)}` +
    `/history?limit=${limit}`;
  const response = await fetch(path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new Error(`signal history failed: ${response.status}`);
  }
  return (await response.json()) as SignalHistoryResponse;
}

/** Fetch signals whose bar timestamp falls within an inclusive range. */
export async function fetchSignalsInRange(
  symbol: string,
  timeframe: string,
  from?: string,
  to?: string,
  token?: string,
): Promise<SignalRangeResponse> {
  const params = new URLSearchParams();
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  const query = params.toString();
  const path =
    `/api/v1/signals/${encodeURIComponent(symbol)}/${encodeURIComponent(timeframe)}` +
    `/range${query ? `?${query}` : ""}`;
  const response = await fetch(path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new Error(`signal range failed: ${response.status}`);
  }
  return (await response.json()) as SignalRangeResponse;
}

/**
 * Plot a signal on a chart.
 *
 * The rule this enforces: the marker goes on the bar whose timestamp equals
 * `signal.timestamp`, at height `signal.price`. Any other placement — shifting a
 * bar forward, using `entry`, using the current price — puts the marker on a
 * candle that did not produce the signal.
 */
export function toChartMarker(signal: TradeSignal): {
  time: string;
  price: number;
  action: SignalAction;
  sl: number;
  tp1: number;
  tp2: number;
} {
  return {
    time: signal.timestamp,
    price: signal.price,
    action: signal.action,
    sl: signal.sl,
    tp1: signal.tp1,
    tp2: signal.tp2,
  };
}