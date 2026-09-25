/**
 * Wire types mirroring the FastAPI response models.
 *
 * FastAPI serialises response models with aliases, so market-data fields use
 * the camelCase names biquote emits (e.g. `dayDiffPercent`), while agent signal
 * models are plain snake_case. `is_tradeable` is a computed field and stays
 * snake_case.
 */

export type MarketState = "open" | "closed" | "unknown";
export type Direction = "BULLISH" | "BEARISH" | "NEUTRAL";
export type Sentiment =
  | "VERY_BULLISH"
  | "BULLISH"
  | "NEUTRAL"
  | "BEARISH"
  | "VERY_BEARISH";
export type Impact = "LOW" | "MEDIUM" | "HIGH";
export type AlertLevel = "NONE" | "MONITOR" | "REDUCE_POSITION_SIZE" | "HALT_TRADING";
export type Decision = "BUY" | "SELL" | "WAIT" | "SKIP";
export type Timeframe = "M1" | "M5" | "M15" | "M30" | "H1" | "H4" | "D1";

/** Timeframes the chart UI exposes (weekly/monthly are aggregated client-side). */
export type ChartTimeframe = Timeframe | "W1" | "MN";

/** Main chart representation. */
export type ChartType = "candlestick" | "line" | "area";

export interface Tick {
  symbol: string;
  description: string;
  bid: number;
  ask: number;
  mid: number;
  spread: number;
  high: number | null;
  low: number | null;
  direction: string;
  dayDiffPercent: number | null;
  timestamp: string;
  source: string;
  marketState: MarketState;
  stale: boolean;
  quoteAgeSeconds: number;
  lastQuoteAt: string | null;
  is_tradeable: boolean;
}

export interface OhlcBar {
  openTime: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  tickVolume: number;
  isOpen: boolean;
  range: number;
}

export interface OhlcSeries {
  symbol: string;
  interval: string;
  bars: OhlcBar[];
}

export interface KeyLevels {
  support: number | null;
  resistance: number | null;
}

export interface IndicatorSnapshot {
  rsi: number | null;
  macd_histogram: number | null;
  macd_cross: string | null;
  ema_fast: number | null;
  ema_slow: number | null;
  ema_cross: string | null;
  atr: number | null;
  adx: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
}

export interface TechnicalSignal {
  agent: string;
  symbol: string;
  timeframe: Timeframe;
  signal: Direction;
  confidence: number;
  key_levels: KeyLevels;
  indicators: IndicatorSnapshot;
  reasoning: string;
  price: number | null;
  generated_at: string;
}

export interface HistoricalReaction {
  symbol: string;
  percent_move: number;
}

export interface NewsSignal {
  agent: string;
  event: string;
  impact: Impact;
  affected_symbols: string[];
  sentiment: Sentiment;
  confidence: number;
  time_until_event: string | null;
  historical_reaction: HistoricalReaction[];
  alert: AlertLevel;
  reasoning: string;
  generated_at: string;
}

export interface RiskCheck {
  name: string;
  passed: boolean;
  blocking: boolean;
  value: number | null;
  threshold: number | null;
  detail: string;
}

export interface RiskAssessment {
  agent: string;
  symbol: string;
  approved: boolean;
  checks: RiskCheck[];
  position_size: number;
  leverage: number;
  stop_loss: number | null;
  take_profit: number | null;
  var_95: number | null;
  reasoning: string;
  generated_at: string;
}

export interface TradeDecision {
  agent: string;
  symbol: string;
  decision: Decision;
  final_score: number;
  technical_score: number;
  news_score: number;
  risk_score: number;
  risk_approved: boolean;
  position_size: number;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  reasoning: string;
  executed: boolean;
  order_id: string | null;
  generated_at: string;
}

export interface CycleResponse {
  symbol: string;
  correlation_id: string;
  technical: TechnicalSignal;
  news: NewsSignal;
  risk: RiskAssessment;
  decision: TradeDecision;
}

export interface Position {
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  entry_price: number;
  stop_loss: number | null;
  take_profit: number | null;
}

export interface HealthResponse {
  status: string;
  environment: string;
  symbols: string[];
}

export interface TickFrameSnapshot {
  type: "snapshot";
  symbols: string[];
  ticks: Record<string, Tick>;
}

export interface TickFrameTick {
  type: "tick";
  tick: Tick;
}

export interface TickFrameError {
  type: "error";
  message: string;
}

export type TickFrame = TickFrameSnapshot | TickFrameTick | TickFrameError;

/** A recorded agent signal from the backend signal store. */
export interface SignalRecord {
  id: string;
  correlation_id: string;
  symbol: string;
  agent: string;
  kind: string;
  direction: string;
  confidence: number;
  created_at: string;
  payload: Record<string, unknown>;
}

export type AgentRuntimeStatus = "active" | "idle" | "error";

export interface AgentStatus {
  name: string;
  status: AgentRuntimeStatus;
  signal_count: number;
  avg_confidence: number;
  last_signal_at: string | null;
}

export interface SymbolStats {
  count: number;
  bullish: number;
  bearish: number;
  neutral: number;
  avg_confidence: number;
}

export interface AgentStats {
  count: number;
  avg_confidence: number;
}

export interface PerformanceStats {
  total_signals: number;
  bullish: number;
  bearish: number;
  neutral: number;
  avg_confidence: number;
  decisions: Record<string, number>;
  by_symbol: Record<string, SymbolStats>;
  by_agent: Record<string, AgentStats>;
  confidence_buckets: number[];
  activity_by_hour: number[];
}

export type AlertPriority = "critical" | "high" | "medium" | "low";

export interface Alert {
  id: string;
  type: string;
  priority: AlertPriority;
  symbol: string;
  title: string;
  detail: string;
  created_at: string;
}

export type AccessRequestStatus = "pending" | "approved" | "rejected";

export interface AccessRequest {
  id: string;
  name: string;
  email: string;
  use_case: string;
  website: string;
  status: AccessRequestStatus;
  created_at: string;
  reviewed_at: string | null;
  token: string | null;
}

export interface MarketSummary {
  lastUpdated?: string;
  [key: string]: unknown;
}

export interface MarketMover {
  symbol: string;
  description: string;
  lastPrice: number;
  changePercent: number;
  changeAmount: number;
  volume: number;
}

export interface NewsArticle {
  title: string;
  description: string | null;
  url: string;
  publisher: string;
  publishedDate: string | null;
  imageUrl: string | null;
  category: string | null;
  language: string | null;
  country: string | null;
}

export interface CalendarEvent {
  id: string;
  eventId: string;
  time: string;
  period: string | null;
  countryCode: string;
  currency: string | null;
  name: string;
  importance: Impact;
  type: string;
  sector: string | null;
  unit: string | null;
  multiplier: string | null;
  digits: number | null;
  actual: number | null;
  forecast: number | null;
  previous: number | null;
  revisedPrevious: number | null;
  revision: number | null;
  timeMode: string;
  sourceUrl: string | null;
  source: string;
}

/** Filters accepted by the signals endpoint. */
export interface SignalFilters {
  symbol?: string;
  agent?: string;
  direction?: string;
  minConfidence?: number;
  limit?: number;
}

/** A registered account shown in the admin users table. */
export interface AdminUser {
  id: string;
  name: string;
  email: string;
  provider: string;
  plan: string;
  analysis_used: number;
  plan_expires_at: string | null;
  created_at: string;
}

/** Summary numbers for the admin overview. */
export interface AdminStats {
  total_users: number;
  users_by_plan: Record<string, number>;
  total_analyses: number;
  total_requests: number;
  pending_requests: number;
  total_payments: number;
  paid_payments: number;
}

/** A billing payment shown in the admin billing table. */
export interface AdminBilling {
  payment_id: string;
  user_email: string;
  plan: string;
  amount: number;
  status: string;
  created_at: string;
}

/** Filters accepted by the calendar endpoint. */
export interface CalendarFilters {
  importance?: Impact;
  countries?: string;
  limit?: number;
}
