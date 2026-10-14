import { AUTH_COOKIE, type AuthResponse, type AuthUser } from "@/lib/auth";
import type {
  AccessRequest,
  AdminBilling,
  AdminStats,
  AdminUser,
  AgentStatus,
  Alert,
  CalendarEvent,
  CalendarFilters,
  CycleResponse,
  HealthResponse,
  MarketMover,
  MarketSummary,
  NewsArticle,
  OhlcSeries,
  PerformanceStats,
  Position,
  SignalFilters,
  SignalRecord,
  Tick,
  Timeframe,
} from "@/lib/types";

/** Base URL of the FastAPI gateway. Override with NEXT_PUBLIC_API_BASE_URL. */
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

/** WebSocket base derived from the HTTP base. */
export const WS_BASE_URL = API_BASE_URL.replace(/^http/, "ws");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Which of the two user-facing analysis models to run.
 *
 * These are display names over two upstream backends, and the mapping is resolved
 * server-side. The client never sees or sends a backend identifier — `xgboost` and
 * `lightgbm` are not part of this screen's vocabulary.
 */
export type ZenmuxModelId = "super" | "flash";

export interface ZenmuxModelOption {
  id: ZenmuxModelId;
  name: string;
  description: string;
}

/** Which engine produced a field: the classifier, or the indicator pass. */
export type ZenmuxReasonSource = "analysis" | "model";

export interface ZenmuxReason {
  detail: string;
  source: ZenmuxReasonSource;
}

/**
 * Timeframes the Zenmux analysis can be read on.
 *
 * M5 and M15 only: the market feed returns roughly three days of M5, which is enough
 * to aggregate M15 but not H1. The classifier always scores M5 regardless — see
 * :data:`ZenmuxAnalysis.model_timeframe`.
 */
export type ZenmuxTimeframe = "M5" | "M15";

export interface ZenmuxAnalysis {
  model_name: string;
  model_description: string;
  symbol: string;
  symbol_label: string;
  /** The timeframe the structure, reasons and levels describe. */
  timeframe: ZenmuxTimeframe;
  /** The timeframe the classifier actually scored, always M5. */
  model_timeframe: string;

  /** From the classifier. */
  direction: "BULLISH" | "BEARISH" | "NEUTRAL";
  confidence: number;
  probability_up: number;
  probability_down: number;

  /** From the indicator pass over the same candles. */
  structure: string;
  structure_detail: string;
  close: number;
  support: number;
  resistance: number;
  atr: number | null;
  rsi: number | null;

  reasons: ZenmuxReason[];
  summary: string;
  updated_at: string;

  /** True when there were too few closed bars to read structure. */
  limited: boolean;
}

export interface PlanInfo {
  plan: string;
  limit: number;
  used: number;
  remaining: number;
  /** Per-UTC-day cap; `-1` means unlimited. */
  daily_limit: number;
  used_today: number;
  remaining_today: number;
  active: boolean;
  expires_at: string | null;
  price_usd: number | null;
  limits: Record<string, number>;
  daily_limits: Record<string, number>;
  prices: Record<string, number>;
}

export interface CheckoutResult {
  payment_id: string;
  plan: string;
  amount: number;
  qr_image: string;
  qr_string: string;
  payment_url: string;
  status: string;
}

export interface VerifyResult {
  paid: boolean;
  status: string;
  plan: string | null;
}

/** Read the auth token from the cookie (browser only). */
export function authToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${AUTH_COOKIE}=([^;]+)`));
  return match ? decodeURIComponent(match[1]) : null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = authToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = `Request failed with ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown; message?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (typeof body.message === "string") detail = body.message;
      else if (body.detail) detail = JSON.stringify(body.detail);
    } catch {
      // keep the default message
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  tick: (symbol: string, allowStale = true) =>
    request<Tick>(
      `/api/v1/tick/${encodeURIComponent(symbol)}?allow_stale=${allowStale}`,
    ),

  ohlc: (symbol: string, interval: Timeframe, limit = 200) =>
    request<OhlcSeries>(
      `/api/v1/ohlc/${encodeURIComponent(symbol)}?interval=${interval}&limit=${limit}`,
    ),

  /**
   * Ask the market analyst. The server fetches the live quote, candles and news
   * for `symbol`/`timeframe` and grounds the answer in them, so only the question
   * and prior turns are sent from the client.
   */
  chat: (input: {
    question: string;
    symbol: string;
    timeframe: Timeframe;
    history?: { role: "user" | "assistant"; content: string }[];
  }) =>
    request<{
      answer: string;
      model: string;
      symbol: string;
      timeframe: Timeframe;
      as_of: string;
      data_status: Record<string, string>;
      snapshot: {
        quote: Record<string, unknown> | null;
        technicals: Record<string, unknown> | null;
        news: { title: string; publisher: string; published: string | null }[];
      };
    }>("/api/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),

  /**
   * Ask Zenmux for an XAU/USD analysis card.
   *
   * Not a language model: the upstream service takes OHLCV and returns a
   * probability, so the turn selects a model rather than being answered. Candles
   * are fetched server-side and the API key never reaches this client.
   *
   * Direction and confidence come from the classifier. Structure, reasons and
   * levels are computed from those same candles by the server's indicator pass,
   * and every reason is tagged with which engine produced it.
   *
   * Confidence upstream is `|p - 0.5| * 2`, which lands between roughly 0.05 and
   * 0.25 on most bars. The card prints the real number rather than scaling it up.
   */
  zenmux: (input: {
    question: string;
    model?: ZenmuxModelId;
    timeframe?: ZenmuxTimeframe;
    history?: { role: "user" | "assistant"; content: string }[];
  }) =>
    request<ZenmuxAnalysis>("/api/v1/zenmux", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: "XAUUSD", ...input }),
    }),

  /** The two selectable analysis models. */
  zenmuxModels: () =>
    request<{ data: ZenmuxModelOption[]; count: number }>("/api/v1/zenmux/models"),

  /** Ask the Raggrap self-improvement engine (context-aware AI assistant). */
  raggrapQuery: (query: string, useCache = true) =>
    request<{
      query: string;
      answer: string;
      warnings_applied: string[];
      was_corrected: boolean;
      cached: boolean;
      timestamp: string;
      reasoning: string | null;
    }>(`/api/v1/raggrap/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, use_cache: useCache, include_explanation: false }),
    }),

  analyze: (symbol: string, timeframes: Timeframe[]) => {
    const query = timeframes.length ? `?timeframes=${timeframes.join(",")}` : "";
    return request<CycleResponse>(
      `/api/v1/analyze/${encodeURIComponent(symbol)}${query}`,
      { method: "POST" },
    );
  },

  positions: () => request<Position[]>("/api/v1/positions"),

  equity: () => request<number>("/api/v1/equity"),

  signals: (filters: SignalFilters = {}) => {
    const params = new URLSearchParams();
    if (filters.symbol) params.set("symbol", filters.symbol);
    if (filters.agent) params.set("agent", filters.agent);
    if (filters.direction) params.set("direction", filters.direction);
    if (filters.minConfidence !== undefined) {
      params.set("min_confidence", String(filters.minConfidence));
    }
    if (filters.limit !== undefined) params.set("limit", String(filters.limit));
    const query = params.toString();
    return request<SignalRecord[]>(`/api/v1/signals${query ? `?${query}` : ""}`);
  },

  agents: () => request<AgentStatus[]>("/api/v1/agents"),

  performance: () => request<PerformanceStats>("/api/v1/performance"),

  alerts: (limit = 50) => request<Alert[]>(`/api/v1/alerts?limit=${limit}`),

  news: (symbol?: string, limit = 15) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (symbol) params.set("symbol", symbol);
    return request<NewsArticle[]>(`/api/v1/news?${params.toString()}`);
  },

  calendar: (filters: CalendarFilters = {}) => {
    const params = new URLSearchParams();
    if (filters.importance) params.set("importance", filters.importance);
    if (filters.countries) params.set("countries", filters.countries);
    if (filters.limit !== undefined) params.set("limit", String(filters.limit));
    const query = params.toString();
    return request<CalendarEvent[]>(`/api/v1/calendar${query ? `?${query}` : ""}`);
  },

  marketMovers: (kind: "gainers" | "losers" | "most-active" = "gainers", limit = 10) =>
    request<MarketMover[]>(`/api/v1/market/movers?kind=${kind}&limit=${limit}`),

  marketSummary: () => request<MarketSummary>("/api/v1/market/summary"),

  // --- Community (social feed) ---
  communityFeed: (tab = "forYou", page = 1, pageSize = 6) =>
    request<import("@/hooks/use-social").SocialPost[]>(
      `/api/v1/community/feed?tab=${tab}&page=${page}&page_size=${pageSize}`,
    ),

  communityUsers: () =>
    request<import("@/hooks/use-social").SocialUser[]>("/api/v1/community/users"),

  communityPost: (postId: string) =>
    request<import("@/hooks/use-social").SocialPost>(`/api/v1/community/posts/${postId}`),

  communityCreatePost: (body: {
    text: string;
    hashtags: string[];
    attachments: import("@/hooks/use-social").PostAttachment[];
  }) =>
    request<import("@/hooks/use-social").SocialPost>("/api/v1/community/posts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  communityToggleLike: (postId: string) =>
    request<import("@/hooks/use-social").SocialPost>(`/api/v1/community/posts/${postId}/like`, {
      method: "POST",
    }),

  communityToggleRepost: (postId: string) =>
    request<import("@/hooks/use-social").SocialPost>(`/api/v1/community/posts/${postId}/repost`, {
      method: "POST",
    }),

  communityToggleBookmark: (postId: string) =>
    request<import("@/hooks/use-social").SocialPost>(`/api/v1/community/posts/${postId}/bookmark`, {
      method: "POST",
    }),

  communityToggleSave: (postId: string) =>
    request<import("@/hooks/use-social").SocialPost>(`/api/v1/community/posts/${postId}/save`, {
      method: "POST",
    }),

  communityToggleMute: (postId: string) =>
    request<import("@/hooks/use-social").SocialPost>(`/api/v1/community/posts/${postId}/mute`, {
      method: "POST",
    }),

  communityBlockPost: (postId: string) =>
    request<import("@/hooks/use-social").SocialPost>(`/api/v1/community/posts/${postId}/block`, {
      method: "POST",
    }),

  communityComments: (postId: string) =>
    request<import("@/hooks/use-social").SocialComment[]>(
      `/api/v1/community/posts/${postId}/comments`,
    ),

  communityAddComment: (
    postId: string,
    body: { text: string; parentId?: string | null },
  ) =>
    request<import("@/hooks/use-social").SocialComment>(
      `/api/v1/community/posts/${postId}/comments`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    ),

  communityCommentLike: (commentId: string) =>
    request<import("@/hooks/use-social").SocialComment>(
      `/api/v1/community/comments/${commentId}/like`,
      { method: "POST" },
    ),

  communityCommentRepost: (commentId: string) =>
    request<import("@/hooks/use-social").SocialComment>(
      `/api/v1/community/comments/${commentId}/repost`,
      { method: "POST" },
    ),

  communityDeleteComment: (commentId: string) =>
    request<null>(`/api/v1/community/comments/${commentId}`, { method: "DELETE" }),

  communityCommentReport: (commentId: string) =>
    request<import("@/hooks/use-social").SocialComment>(
      `/api/v1/community/comments/${commentId}/report`,
      { method: "POST" },
    ),

  communityFollowUser: (userId: string) =>
    request<{ following: boolean }>(`/api/v1/community/users/${userId}/follow`, {
      method: "POST",
    }),

  communityUnfollowUser: (userId: string) =>
    request<{ following: boolean }>(`/api/v1/community/users/${userId}/follow`, {
      method: "DELETE",
    }),

  communityNotifications: () =>
    request<import("@/hooks/use-social").SocialNotification[]>("/api/v1/community/notifications"),

  communityMarkNotificationsRead: () =>
    request<{ mark: number }>("/api/v1/community/notifications/read", { method: "POST" }),

  communitySearch: (q: string) =>
    request<{
      users: import("@/hooks/use-social").SocialUser[];
      posts: import("@/hooks/use-social").SocialPost[];
      markets: string[];
      hashtags: string[];
      topics: string[];
    }>(`/api/v1/community/search?q=${encodeURIComponent(q)}`),

  communityTrending: () =>
    request<{
      markets: import("@/hooks/use-social").TrendingMarket[];
      topics: import("@/hooks/use-social").TrendingTopic[];
      suggested: import("@/hooks/use-social").SuggestedTrader[];
    }>("/api/v1/community/trending"),

  register: (body: {
    name: string;
    email: string;
    password: string;
    turnstile_token?: string;
  }) =>
    request<AuthResponse>("/api/v1/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  login: (body: { email: string; password: string }) =>
    request<AuthResponse>("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  me: () => request<AuthUser>("/api/v1/auth/me"),

  authConfig: () => request<{ google: boolean }>("/api/v1/auth/config"),

  applyForAccess: (body: {
    name: string;
    email: string;
    use_case: string;
    website: string;
    turnstile_token?: string;
  }) =>
    request<{ status: string; id: string; message: string }>("/api/v1/access/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  adminSession: () =>
    request<{ admin: boolean; email: string; name: string }>("/api/v1/admin/session"),

  adminRequests: () => request<AccessRequest[]>("/api/v1/admin/requests"),

  adminUsers: () => request<AdminUser[]>("/api/v1/admin/users"),

  adminStats: () => request<AdminStats>("/api/v1/admin/stats"),

  adminBilling: () => request<AdminBilling[]>("/api/v1/admin/billing"),

  approveRequest: (id: string) =>
    request<AccessRequest>(`/api/v1/admin/requests/${id}/approve`, { method: "POST" }),

  rejectRequest: (id: string) =>
    request<AccessRequest>(`/api/v1/admin/requests/${id}/reject`, { method: "POST" }),

  billingPlan: () => request<PlanInfo>("/api/v1/billing/plan"),

  // The free Pro trial is discontinued; the endpoint answers 410 Gone. There is
  // deliberately no client method for it.

  billingCheckout: (plan: "starter" | "pro" | "ultra") =>
    request<CheckoutResult>("/api/v1/billing/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan }),
    }),

  billingVerify: (paymentId: string) =>
    request<VerifyResult>("/api/v1/billing/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payment_id: paymentId }),
    }),
};

/** Absolute URL that starts the Google OAuth flow on the backend. */
export function googleLoginUrl(turnstileToken?: string, next?: string): string {
  const url = new URL(`${API_BASE_URL}/api/v1/auth/google/login`);
  if (turnstileToken) url.searchParams.set("turnstile_token", turnstileToken);
  if (next) url.searchParams.set("next", next);
  return url.toString();
}
