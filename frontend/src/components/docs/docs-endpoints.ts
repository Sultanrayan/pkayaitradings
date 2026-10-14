/**
 * The API surface documented on the Developer page.
 *
 * Kept as data rather than markup so the endpoint table, the "Try it" panel and the
 * search index all read from one place and cannot disagree.
 *
 * Every path and payload below was read off the running service — the routes in
 * `orchestrator/main.py` and the response models in `shared/` — so a request copied out
 * of these docs is a request that exists. Two consequences worth knowing:
 *
 * * Health lives at `/health`, not under the versioned prefix, because it is on the
 *   service's `_PUBLIC_PATHS` allow-list and is probed before auth exists.
 * * The candle route is `/api/v1/ohlc/{symbol}`. There is no `/api/v1/candles` alias.
 *
 * `paths` are full paths from the origin, which is why `/health` sits alongside
 * `/api/v1/...` entries here without producing a nonsensical request URL.
 */

/** Origin serving both the docs and the API. */
export const API_ORIGIN = "https://trade.pkay.fun";

/** Versioned base path every authenticated route hangs off. */
export const API_BASE_URL = `${API_ORIGIN}/api/v1`;

export interface EndpointParam {
  name: string;
  example: string;
  description: string;
  required?: boolean;
}

export interface ApiEndpoint {
  /** Anchor id, so sidebar and table rows can be deep-linked. */
  id: string;
  method: "GET" | "POST";
  /** Full path from {@link API_ORIGIN}, e.g. `/api/v1/tick/XAUUSD`. */
  path: string;
  summary: string;
  description: string;
  params: EndpointParam[];
  /** Sample payload returned by the "Try it" panel. */
  sampleResponse: string;
}

export const API_ENDPOINTS: ApiEndpoint[] = [
  {
    id: "endpoint-health",
    method: "GET",
    path: "/health",
    summary: "Health check",
    description:
      "Liveness and readiness probe. Sits outside the versioned prefix and needs no authentication, so it can be polled before you hold a token.",
    params: [],
    sampleResponse: `{
  "status": "ok",
  "environment": "production",
  "symbols": ["XAUUSD", "BTCUSD"],
  "redis": "ok",
  "degraded": null
}`,
  },
  {
    id: "endpoint-tick-xauusd",
    method: "GET",
    path: "/api/v1/tick/XAUUSD",
    summary: "Latest price",
    description:
      "The current quote for one symbol. The feed is a CFD broker feed, so `last` and `volume` are always zero — read `mid`, or `bid`/`ask` for the spread.",
    params: [
      {
        name: "symbol",
        example: "XAUUSD",
        description: "Instrument ticker. XAUUSD or BTCUSD.",
        required: true,
      },
      {
        name: "allow_stale",
        example: "true",
        description: "Serve the last known quote when the feed is behind. Defaults to true.",
      },
    ],
    sampleResponse: `{
  "symbol": "XAUUSD",
  "description": "Gold vs US Dollar",
  "bid": 4140.58,
  "ask": 4140.7,
  "mid": 4140.64,
  "spread": 0.12,
  "high": 4152.1,
  "low": 4128.44
}`,
  },
  {
    id: "endpoint-ohlc-xauusd",
    method: "GET",
    path: "/api/v1/ohlc/XAUUSD",
    summary: "Candle series",
    description:
      "OHLCV candles for one symbol and interval, oldest first. This is the series the agents analyse.",
    params: [
      {
        name: "symbol",
        example: "XAUUSD",
        description: "Instrument ticker. XAUUSD or BTCUSD.",
        required: true,
      },
      {
        name: "interval",
        example: "H1",
        description:
          "Candle size: M1, M5, M15, M30, H1, H4 or D1. Defaults to H1.",
      },
      {
        name: "limit",
        example: "200",
        description: "Number of candles, 1 to 1000. Defaults to 200.",
      },
    ],
    sampleResponse: `{
  "symbol": "XAUUSD",
  "interval": "H1",
  "bars": [
    {
      "openTime": "2026-10-05T11:00:00Z",
      "open": 4132.18,
      "high": 4144.9,
      "low": 4126.05,
      "close": 4140.64,
      "volume": 0,
      "tickVolume": 1842,
      "isOpen": false
    }
  ]
}`,
  },
  {
    id: "endpoint-analyze",
    method: "POST",
    path: "/api/v1/analyze",
    summary: "Run agent cycles",
    description:
      "Runs the full pipeline for each requested symbol and returns one cycle per symbol, so the decision can be traced rather than taken on trust.",
    params: [
      {
        name: "symbols",
        example: '["XAUUSD"]',
        description: "Instruments to analyse. Defaults to every configured symbol.",
      },
      {
        name: "timeframes",
        example: '["H1"]',
        description:
          "Intervals to align across: M1, M5, M15, M30, H1, H4 or D1.",
      },
    ],
    sampleResponse: `[
  {
    "symbol": "XAUUSD",
    "correlation_id": "cyc_01JQZ8K3M",
    "technical": { "direction": "short", "confidence": 0.79 },
    "news": { "direction": "bullish", "confidence": 0.18 },
    "risk": { "approved": true, "position_size": 0.24 },
    "decision": { "action": "sell", "confidence": 0.79 }
  }
]`,
  },
];

/**
 * Grouped index backing the search palette's "API Endpoints" section.
 *
 * Each entry points at its row's anchor on the Developer page, so selecting a result
 * scrolls to that endpoint rather than jumping to the top of the section.
 */
export const ENDPOINT_INDEX = API_ENDPOINTS.map((endpoint) => ({
  group: "API Endpoints",
  label: `${endpoint.method} ${endpoint.path}`,
  href: "/docs/api-reference",
  hash: endpoint.id,
  keywords: `${endpoint.summary} ${endpoint.description} ${endpoint.method} ${endpoint.path}`,
}));