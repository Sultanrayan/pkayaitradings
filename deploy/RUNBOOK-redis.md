# Redis / Celery runbook

Operational reference for the Redis message bus and the Celery worker + beat
that drive the analysis cycle and the Signal Updater.

## What Redis is for

Three things, all on the same instance:

1. **Message bus.** Every agent publishes its output on a `signals.<agent>`
   channel. Cross-process subscribers read them via `signals.*` glob.
2. **Celery broker.** The queue the beat schedule publishes tasks onto.
3. **Celery result backend.** Task return values, used for verification.

If Redis is unreachable the API still serves — `create_message_bus` falls back
to `InMemoryMessageBus`, so the dashboard, chat and REST endpoints keep working
and the in-process agents still publish to each other. What is lost:

- **the Celery worker and beat cannot run at all** (no broker), so no analysis
  cycle is scheduled and **the Signal Updater never runs**;
- cross-process subscribers see nothing;
- signals published by the API are not visible outside that process.

This degradation is logged at **ERROR** as `bus.redis_degraded`, with the
target URL. Treat that event as a real incident: the API looks healthy in
`/health` while silently losing all background work.

## Why `REDIS_URL` uses service DNS

Inside the api container, `localhost` is the *container's* loopback, not the
host's. The URL must be `redis://redis:6379/0`, where `redis` is the compose
service name resolved over the internal network. `redis://localhost:6379` fails
with `Errno 111 Connection refused` even when Redis is running, which is a
confusing symptom — the process is up, the config is wrong.

The code default in `shared/config.py` stays `redis://localhost:6379/0`
because that is correct for local development. Production supplies its own value
via `REDIS_URL` in `.env.production`.

Redis publishes **no host ports**. It is reachable only on the compose network.

## Checking Redis health

```bash
cd /opt/pkay

# 1. PING from inside the container (expects PONG)
docker exec pkay-tdai-redis-1 redis-cli ping

# 2. Container state (should be "Up ... (healthy)")
docker compose -f docker-compose.prod.yml --env-file .env.production ps

# 3. Memory / persistence
docker exec pkay-tdai-redis-1 redis-cli info memory | grep -E "used_memory_human|maxmemory_human"
docker exec pkay-tdai-redis-1 redis-cli info persistence | grep -E "aof_enabled|rdb_last_bgsave_status"
```

`aof_enabled:1` confirms `--appendonly yes` is active, so Celery's schedule and
queued tasks survive a restart.

## Checking the bus connection

```bash
# Is the API on the Redis bus or the in-memory fallback?
curl -s https://trade.pkay.fun/health | python3 -m json.tool
```

```json
{
  "status": "ok",
  "environment": "production",
  "symbols": ["XAUUSD", "BTCUSD"],
  "redis": "ok",
  "degraded": null
}
```

- `redis: "ok"`, `degraded: null` — healthy.
- `redis: "unavailable"`, `degraded: "in_memory_bus"` — **degraded**. The API
  works, but the worker, beat and the Signal Updater are down.

`/health` reports the bus type, not a live ping. `RedisMessageBus` is only ever
constructed after a successful ping at startup, so the field is accurate as of
process start. **If Redis dies after startup, this field stays `ok` until the
API restarts** — check the logs and the container state rather than trusting it
alone.

Grep for the degradation event:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production logs api \
  | grep bus.redis_degraded
```

## Checking the Celery beat schedule

```bash
# Both tasks must be registered
docker exec pkay-tdai-beat-1 celery -A orchestrator.scheduler inspect registered

# Beat's configured schedule
docker exec pkay-tdai-beat-1 python -c "
from orchestrator.scheduler import celery_app
for name, entry in celery_app.conf.beat_schedule.items():
    print(f\"{name} -> {entry['task']} every {entry['schedule']}s\")
"

# Live worker (should show online, concurrency 2)
docker exec pkay-tdai-worker-1 celery -A orchestrator.scheduler inspect ping
docker compose -f docker-compose.prod.yml --env-file .env.production logs worker --tail 20
```

Expected schedule:

```
analyze-all-symbols    -> orchestrator.scheduler.analyze_all_symbols    every 300.0s
update-active-signals  -> orchestrator.scheduler.update_active_signals  every 60.0s
```

`update_active_signals` returns immediately with `{"enabled": false, ...}` while
`signal_update_enabled` is `False`. That is expected, not an error.

## Recovering from a Redis outage

Redis is `restart: unless-stopped` and the api/worker/beat all declare
`depends_on: redis: condition: service_healthy`, so a crash is usually
self-healing. Escalate in this order:

```bash
cd /opt/pkay
COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.production"

# 1. Is it up?
$COMPOSE ps redis
docker exec pkay-tdai-redis-1 redis-cli ping        # expect PONG

# 2. Restart Redis alone
$COMPOSE restart redis

# 3. Redis recovered, but the API cached the degraded decision at startup.
#    create_message_bus runs once and never retries, so restart the API too.
$COMPOSE restart api

# 4. Bring the background services back (they crash-loop without a broker)
$COMPOSE up -d worker beat

# 5. Verify
curl -s https://trade.pkay.fun/health          # expect "redis": "ok"
$COMPOSE logs api --tail 20 | grep -c bus.redis_degraded   # expect 0 for the new start
$COMPOSE logs worker --tail 10
```

**Step 3 is the one people miss.** The fallback is decided once at startup. An
API started while Redis was down stays on the in-memory bus even after Redis
recovers, so `/health` keeps reporting `unavailable` until the API is
restarted. There is no reconnect loop.

## Measuring LLM cost per cycle

Beat runs `analyze_all_symbols` every 900s (`analysis_interval_seconds`). A cycle
touches every symbol in `trading_symbols` and makes **7 billed LLM calls per
symbol**, so 14 calls per cycle at the current 2 symbols.

Cost is logged directly — no dashboard reconciliation needed.

```bash
cd /opt/pkay
COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.production"

# Tokens, cost and cache rate for the last cycles, straight from the worker log
$COMPOSE logs worker 2>&1 | grep "pipeline.cycle_complete" | tail -5

# Per-call token usage
$COMPOSE logs worker 2>&1 | grep "llm.usage" | tail -20

# Interval, symbols, and the billing constants, straight from the beat container
docker exec pkay-tdai-beat-1 python -c "
from shared.config import UNITS_PER_USD, get_settings
from shared.llm import COST_PER_TOKEN_UNITS
s = get_settings()
print('symbols         :', s.trading_symbols)
print('interval_seconds:', s.analysis_interval_seconds)
print('units_per_usd   :', UNITS_PER_USD)
print('units_per_token :', COST_PER_TOKEN_UNITS)
"
```

Do **not** grep logs for bare numbers like `429` — Celery task UUIDs contain
matching substrings and will report phantom rate limits. Match the structured
fields instead:

```bash
$COMPOSE logs worker 2>&1 | grep -cE "llm\.retryable_status"   # real 429s
$COMPOSE logs worker 2>&1 | grep -c "llm.usage_missing"        # calls with no usage
```

### The cost formula

```
cost_units = (prompt_tokens + completion_tokens) * COST_PER_TOKEN_UNITS
cost_usd   = cost_units / UNITS_PER_USD
```

- `COST_PER_TOKEN_UNITS = 4` (`shared/llm.py`)
- `UNITS_PER_USD = 25_000_000` (`shared/config.py`), i.e. $1 = 25M units
- One token costs 4 units = **$0.00000016**

Both constants come from the provider's published pricing and are module
constants, not `Settings` fields, so no environment variable can misprice a log
line. If the provider changes its rate, these are the two places to correct.

**Cached tokens are billed at the same rate as fresh ones**, so prompt caching
does not reduce spend under this pricing — it only reduces latency. Analysis
prompts also have stable prefixes of only ~46–57 tokens against a ~1024-token
cacheable floor, so a cache hit is not achievable by restructuring prompts.
Treat `llm_cache_hit_rate` as a diagnostic, not a cost lever.

### Measured baseline

| Metric | Value |
|---|---|
| `trading_symbols` | 2 (XAUUSD, BTCUSD) |
| Symbols per cycle | 2 |
| LLM calls per cycle | 14 (7 per symbol) |
| Wall time per cycle | ~77s |
| Interval | 900s → 96 cycles/day |
| Calls per day | 1,344 |
| Tokens per cycle | ~9,900 |
| Tokens per day | ~951,000 |
| **Cost per day** | **~$0.15** |
| **Cost per month** | **~$4.56** |

For reference at other intervals: 600s ≈ $6.84/month, 300s ≈ $13.68/month.
Enabling the Signal Updater adds roughly $3–5/month on top.

Counters are cumulative **per worker process**, so the second symbol's
`cycle_complete` line includes the first symbol's usage. Restarting the worker
resets them.

## Pausing beat if cost is prohibitive

Beat is the only thing that spends money on a timer. Stop it without touching
the API:

```bash
cd /opt/pkay
# Stop scheduling. The API, frontend and Redis keep serving.
docker compose -f docker-compose.prod.yml --env-file .env.production stop beat

# Also drain the worker so no queued cycle runs when beat comes back
docker compose -f docker-compose.prod.yml --env-file .env.production stop worker

# Resume
docker compose -f docker-compose.prod.yml --env-file .env.production up -d worker beat

# Verify nothing is still firing
docker compose -f docker-compose.prod.yml --env-file .env.production logs beat --tail 5
```

To slow it down instead of stopping it, raise `ANALYSIS_INTERVAL_SECONDS` in
`.env.production` and restart beat. To make the Signal Updater cheap without
touching beat, leave `signal_update_enabled` false — its task then returns
immediately.

## Checking the parser still matches the log format

After any change to what the pipeline logs, check the parser before trusting a
report:

```bash
bash deploy/report-24h.sh --validate
```

This asks one question — *does this parser still read this format* — and prints
parse coverage, field presence, unknown fields and observed event names. It emits
**no statistics and no verdict**, so its output can never be mistaken for the
window's result and quoted as one.

What it catches:

| Signal | Meaning |
|---|---|
| `UNPARSABLE, not a task line` > 0 | A real event stopped parsing. Report figures are suspect |
| `MISSING COUNTERS:` | A counter was renamed. It would difference as 0 — silently |
| `MISSING IDENTIFIERS:` | `symbol` / `correlation_id` / `timestamp` gone; cycles unidentifiable |
| `Celery task-result lines` > 0 | **Normal, not drift.** Celery truncates long task return values (`'symb...', ...}}]`), which cannot be `literal_eval`'d |

Verified against the live log after the token and cost counters were added:

```
total lines                    401
lines carrying a dict          194
parsed as structured events    190
Celery task-result lines       4  (truncated return values, not events)
UNPARSABLE, not a task line    0
cycle_complete lines            8
of those, duration matched     4/4
all 13 counters + 3 identifiers present on 8/8 cycle lines
```

Seven unknown fields were reported (`decision`, `score`, `traded`, `logger`,
`level`, `llm_cost_usd`, `llm_cache_hit_rate`). All benign — the parser derives
cost from `cost_units` for precision and reads the rate rather than the rounded
field, which is what the `llm_cost_usd` listing above is telling you.

## Per-cycle stability report

For distributions rather than a point reading — wall time, cost, and pressure
counters per cycle, differenced rather than read from cumulative totals:

```bash
bash deploy/report-24h.sh --since-hours 24 --label "24h stability window"
```

The parser (`deploy/report_24h.py`) reads each log line's event dict by exact
key and differences the cumulative counters, so a worker restart mid-window
re-bases instead of looking like a spend spike. It prints `(no data)` rather
than extrapolating from a window under an hour.

Prefer it over the ad-hoc greps above. Two of those produced confident wrong
answers: a bare `429` matched digit runs inside Celery task UUIDs, and
`llm.usage_missing` matched the `llm_usage_missing` field on unrelated cycle
lines. `tests/test_report_24h.py` pins both regressions.

## Signal Updater — known limitations

The updater is deployed but **disabled**. Before enabling it, read these: they
are deliberate, accepted, and observable rather than bugs to chase mid-window.

Source detail is in the `agents/signal_updater/agent.py` module docstring under
"Known limitations".

### The cooldown window is one global setting, not per symbol

`signal_update_cooldown_seconds` is 600s and **all symbols share that one
window**. The state is tracked per symbol — each has its own
`last_evaluated_at` and expires independently — but the duration is a single
number, not a per-symbol override.

Why it exists: `PRICE_MOVE` fires on any 0.3% excursion from entry, so on a
liquid pair it is effectively always true. Without a gate, the 60s beat would
mean a paid three-agent chain per symbol per minute.

What it means operationally: gold and bitcoin are evaluated on the same clock,
even though a 0.3% move means something different for each. Expect at most
6 evaluations/hour/symbol. If one symbol dominates the cost, per-symbol windows
would be the fix and they need their own settings surface.

A skipped evaluation does **not** refresh the timestamp. If it did, a 60s beat
against a 600s cooldown would extend the window indefinitely and the updater
would never run again. Only a completed evaluation sets it.

### A candle close during a cooldown is dropped, not queued

`scan` advances the bar watermark on every pass, and the scheduler only calls
`evaluate` when `scan` reports a trigger. So if a candle closes while the
cooldown is still running: `scan` sees `CANDLE_CLOSE`, `evaluate` refuses, and
the *next* scan finds the bar already consumed and reports nothing. That close
never reaches an evaluation.

**Impact:** an update can be up to one full bar late. Nothing is corrupted and
no trigger is acted on twice — it is delayed or missed, not misapplied.

**How to watch it:** dropped triggers log at WARNING with
`note=trigger_dropped_cooldown` and are counted per symbol in
`cooldown_state()`. A non-zero count is expected and healthy. A count that
scales with triggers rather than staying a small fraction would mean the
cooldown is starving the updater and 600s should be reconsidered.

Queuing triggers across the window would fix this and is deliberately out of
scope until the counter shows it matters.

### Stop moves are advisory only

A KEEP/ADJUST/FLIP can move a stop level, and the dashboard renders the move,
but there is **no broker amend path** — nothing is sent to an execution venue.
The move is recorded and shown; it is not enforced. Logged at WARNING when it
applies so the gap is visible rather than assumed.

### Reading these from the logs

```bash
cd /opt/pkay
COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.production"
$COMPOSE logs worker 2>&1 | grep -c "'event': 'signal_updater.trigger_dropped'"
$COMPOSE logs worker 2>&1 | grep -c "'event': 'signal_updater.cooldown_skipped'"
```

Both are normal once enabled. What is *not* normal is a rising
`trigger_dropped` count with zero `triggered` evaluations, which means the
cooldown is rejecting everything.

## Related known issues

- **`/health` cannot detect a post-startup Redis death** (design choice: no
  network call on the liveness path). Recovery of that detection would need a
  periodic background check, not a probe change.
- **No reconnect loop.** `create_message_bus` decides once at startup.
  Repeated degraded startups in the logs mean this should be added; the log event
  to emit on recovery is `bus.redis_reconnected`, which does not exist yet
  because there is no reconnect path to fire it from.
- **`signal_update_enabled` is still `False`.** The updater is deployed dark
  pending 24 hours of measured beat cost. Cost is no longer the blocker
  (~$4.56/month); the gate is the stability window.
