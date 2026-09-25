# Pkay TDAI — Backend Developer Guide

FastAPI gateway + multi-agent analysis engine for Gold (XAUUSD) and Bitcoin (BTCUSD).

- Python 3.11+, FastAPI, httpx, Pydantic v2
- Four agents: **Technical Analyst**, **News Monitor**, **Risk Manager**, **Decision Maker**
- Persistent user/plan/billing data is JSON in `DATA_DIR` (production mounts a Docker volume)
- Auth: Google OAuth + email/password (bearer tokens); admin allow-list; Khpay KHQR billing

---

## 1. Running the server

### Local development

```powershell
# from the repository root
.\.venv\Scripts\python.exe -m uvicorn orchestrator.main:app --reload --host 0.0.0.0 --port 8000
```

Server: `http://localhost:8000` · health probe: `http://localhost:8000/health`

> Interactive docs (`/docs`, `/redoc`) are off by default. Enable them for local work with `EXPOSE_API_DOCS=true` in `.env`.

### Production (Docker)

```bash
cd /opt/pkay
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
# or use the safe redeploy helper (backs up data first)
bash deploy/redeploy.sh
```

### Tests / lint

```bash
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m ruff check agents orchestrator shared tests
.\.venv\Scripts\python.exe -m mypy agents orchestrator shared
```

---

## 2. Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` \| `staging` \| `production` |
| `AUTH_SECRET` | dev-only | Signs session + API tokens (regenerate in prod) |
| `AUTH_REQUIRED` | `false` | Require a bearer token on every `/api/v1/*` route |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | — | Google OAuth sign-in |
| `GOOGLE_REDIRECT_URI` | `http://localhost:8000/api/v1/auth/google/callback` | OAuth callback |
| `FRONTEND_URL` | `http://localhost:3000` | Where OAuth redirects after login |
| `PUBLIC_BASE_URL` | `https://trade.pkay.fun` | Public origin (webhooks, logos) |
| `ADMIN_EMAILS` | `menmengleapx1@gmail.com` | Admin allow-list (comma separated) |
| `LLM_PROVIDER` | `none` | `openai` (any OpenAI-compatible) \| `none` |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | — | LLM gateway used by the agents |
| `DATA_DIR` | empty | Persist users/requests/payments as JSON here |
| `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY` | empty | Cloudflare Turnstile on register/apply |
| `KHPAY_API_KEY` | empty | Khpay KHQR payments for plan upgrades |
| `BREVO_API_KEY` | — | Transactional email (access tokens) |
| `PLAN_*` / `MEMORY_*` / `HMM_*` | sane defaults | Plans, limits, intelligence layer |

Full list: `.env.example`.

---

## 3. Authentication

* **Bearer tokens** — send `Authorization: Bearer <token>`. Tokens come from `POST /api/v1/auth/register` or `/login` (`token` field), or the Google OAuth flow.
* **Public routes** (no token) — `/health`, `/api/v1/auth/*`, `/api/v1/access/apply`, `/api/v1/agents/capabilities`, `/api/v1/billing/webhook`.
* **Admin routes** — `/api/v1/admin/*` require a bearer token whose account email is on `ADMIN_EMAILS` (otherwise `403`).
* **Developer API** — approved developers get a long-lived `scope=developer` token, valid only for `/api/v1/agents/*`.

**Plan enforcement** — `/v1/analysis`, `/api/v1/analyze/*` consume one analysis per call against the caller's plan (Free = 20/mo, Pro = 150/mo, Ultra = unlimited). Exhausted quota returns `402`.

---

## 4. Endpoints

### System
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | — | Liveness probe → `{status, environment, symbols}` |

### Auth
| Method | Path | Auth | Request / Response |
|---|---|---|---|
| POST | `/api/v1/auth/register` | — | `{name, email, password, turnstile_token?}` → `{token, user}` |
| POST | `/api/v1/auth/login` | — | `{email, password}` → `{token, user}` |
| GET | `/api/v1/auth/me` | ✓ | Current user |
| GET | `/api/v1/auth/config` | — | `{google: bool}` |
| GET | `/api/v1/auth/google/login` | — | `?turnstile_token=&next=` → 307 to Google |
| GET | `/api/v1/auth/google/callback` | — | `?code=&state=` → 307 (sets session cookie) |

### Analysis (the four agents)
| Method | Path | Auth | Description |
|---|---|---|---|
| **POST** | **`/v1/analysis`** | ✓ | **Canonical single endpoint.** `{symbol, timeframes?}` → full cycle (`technical`, `news`, `risk`, `decision`). Runs all four agents. |
| POST | `/api/v1/analyze/{symbol}` | ✓ | Same as above via path param `?timeframes=M5,H1,H4` |
| POST | `/api/v1/analyze` | ✓ | Batch: `{symbols: [...], timeframes?}` → `[cycle]` |

`CycleResponse`:
```json
{
  "symbol": "XAUUSD",
  "correlation_id": "...",
  "technical": { "signal": "BEARISH", "confidence": 0.43, "timeframe": "H1", "indicators": {...}, "reasoning": "..." },
  "news":       { "sentiment": "NEUTRAL", "confidence": 0.5, "impact": "LOW", "reasoning": "..." },
  "risk":       { "approved": true, "position_size": 1.2, "checks": [...], "reasoning": "..." },
  "decision":   { "decision": "WAIT", "final_score": 0.48, "executed": false, "reasoning": "..." }
}
```

### Developer agents API (bearer API token, `scope=developer`)
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/agents/capabilities` | Capability manifest (public) |
| POST | `/api/v1/agents/technical` | Run only the Technical Analyst |
| POST | `/api/v1/agents/news` | Run only the News Monitor |
| POST | `/api/v1/agents/risk` | Run only the Risk Manager |
| POST | `/api/v1/agents/decide` | Run only the Decision Maker |
| POST | `/api/v1/agents/analyze` | Full cycle (like `/v1/analysis`) |

### Market data
| Method | Path | Params / Notes |
|---|---|---|
| GET | `/api/v1/tick/{symbol}` | `?allow_stale=` latest tick |
| GET | `/api/v1/ohlc/{symbol}` | `?interval=M1..D1&limit=` candles |
| GET | `/api/v1/news` | `?symbol=&limit=` headlines |
| GET | `/api/v1/calendar` | `?importance=LOW,MEDIUM,HIGH&countries=&limit=` economic calendar |
| GET | `/api/v1/market/movers` | `?kind=gainers\|losers\|most-active&limit=` |
| GET | `/api/v1/market/summary` | Market snapshot |

### Signals / agents / analytics
| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/signals` | `?symbol=&agent=&direction=&min_confidence=&limit=` recorded agent signals |
| GET | `/api/v1/agents` | Agent runtime status + signal counts |
| GET | `/api/v1/performance` | Signal/decision statistics |
| GET | `/api/v1/alerts` | `?limit=` risk/news alerts |

### Execution (paper)
| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/positions` | Open paper positions |
| GET | `/api/v1/equity` | Current paper equity |

### Plans & billing (auth; webhook public)
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/billing/plan` | Current plan, usage, catalogue |
| POST | `/api/v1/billing/trial` | Grant free 2-month Pro trial (idempotent) |
| POST | `/api/v1/billing/checkout` | `{plan: "pro"\|"ultra"}` → KHQR payment (`qr_image`) |
| POST | `/api/v1/billing/verify` | `{payment_id}` → re-check payment; activates plan when paid |
| POST | `/api/v1/billing/webhook` | Khpay notification (server-to-server) |

### Admin (admin allow-list only)
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/admin/session` | Verify admin identity |
| GET | `/api/v1/admin/users` | All accounts (plan, usage, expiry) |
| GET | `/api/v1/admin/stats` | Totals: users, plans, analyses, requests, payments |
| GET | `/api/v1/admin/billing` | Payment history |
| GET | `/api/v1/admin/requests` | Developer access requests |
| POST | `/api/v1/admin/requests/{id}/approve` | Approve → email token |
| POST | `/api/v1/admin/requests/{id}/reject` | Reject request |

### Access
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/access/apply` | `{name, email, use_case, website, turnstile_token?}` → `202` review message |

### WebSocket
| Path | Params | Notes |
|---|---|---|
| `/ws/ticks` | `?symbols=XAUUSD,BTCUSD&token=` | Live tick stream; `token` required when `AUTH_REQUIRED=true` |

---

## 5. The four agents

1. **Technical Analyst** — indicators + multi-timeframe confirmation + order-flow absorption → `TechnicalSignal`.
2. **News Monitor** — economic calendar + headlines + sentiment classifier → `NewsSignal`.
3. **Risk Manager** — VaR, position sizing, drawdown and stop checks (can veto) → `RiskAssessment`.
4. **Decision Maker** — regime-aware geometric aggregation + cross-checks + optional LLM review → `TradeDecision`.

Resilience: every agent validates its output (Pydantic) and is wrapped in a circuit breaker; `503` is returned when a circuit is open.

---

## 6. Common errors

| Code | Meaning |
|---|---|
| `401` | Missing/invalid bearer token |
| `402` | Plan analysis quota exhausted |
| `403` | Not authorized (non-admin on admin routes, or API token on non-agent routes) |
| `422` | Validation error (bad body/params) |
| `502` | Upstream failure (biquote, Khpay, LLM) |
| `503` | Circuit open / service not configured |