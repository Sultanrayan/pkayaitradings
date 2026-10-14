# Deployment

Single UpCloud server: Caddy (TLS + single origin) → Next.js frontend and the
FastAPI gateway. Only Caddy exposes ports 80/443.

## Persistent data

User accounts and developer access requests are stored as JSON on the
`pkay_data` Docker volume (the API runs with `DATA_DIR=/data`):

- `/data/users.json`
- `/data/access_requests.json`

Without `DATA_DIR` the API keeps them in memory only — fine for local
development, **never** for production. The prod compose sets it and mounts the
volume, so `up -d --build` no longer drops accounts.

> A disk-level rebuild (OS reinstall) destroys Docker volumes too. Always copy
> the backup archive **off the server**.

## Redeploy

```bash
cd /opt/pkay
bash deploy/redeploy.sh          # backs up data, then rebuilds + restarts
```

Or manually:

```bash
bash deploy/backup-data.sh
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
scp -i ~/.ssh/pkay_upcloud backups/pkay-data-*.tar.gz root@94.237.74.255:/root/
```

## Runbooks

- `RUNBOOK-redis.md` — Redis/Celery operations, how LLM cost is derived and read
  from the logs, and the Signal Updater's known limitations.
- `ENABLE-signal-updater.md` — pre-flight checklist for turning on
  `signal_update_enabled`, the two-part flip procedure, and the rollback.
- `verify-signal-updater-flip.sh` — proves the flip procedure end to end in an
  isolated compose project. Safe to run at any time; touches no production
  container, env file or queue, and cleans up after itself.

Both are read-only with respect to production until you act on them. The report
script they reference is:

```bash
bash deploy/report-24h.sh --since-hours 24 --label "24h stability window"
```

It builds per-cycle distributions from worker logs rather than trusting the
cumulative counters, so deploy-time worker restarts do not distort the figures.
Never grep these logs for bare numbers — Celery task UUIDs contain digit runs
that match `429`, and a dotted event name also matches the underscored field on
unrelated lines. Match on `'event': 'name'` instead.

## Restore after a disk rebuild

```bash
git clone <repo> /opt/pkay && cd /opt/pkay
cp /path/to/.env.production .          # from your secret store
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
bash deploy/restore-data.sh /root/pkay-data-YYYYMMDD-HHMMSS.tar.gz
```

## Verification checklist

```bash
curl -I https://trade.pkay.fun                       # 200 + valid cert
curl -s https://trade.pkay.fun/health                # {"status":"ok",...}
curl -s https://trade.pkay.fun/api/v1/auth/config    # {"google":true}
# no token → must fail:
curl -s -o /dev/null -w '%{http_code}\n' https://trade.pkay.fun/api/v1/signals   # 401
```

Admin console: sign in (standard email/password or Google), then open the secret
path `/pkay-control-x7q9` with the allow-listed email.
