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

export interface PlanInfo {
  plan: string;
  limit: number;
  used: number;
  remaining: number;
  active: boolean;
  expires_at: string | null;
  price_usd: number | null;
  limits: Record<string, number>;
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

  billingTrial: () =>
    request<PlanInfo>("/api/v1/billing/trial", {
      method: "POST",
    }),

  billingCheckout: (plan: "pro" | "ultra") =>
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
