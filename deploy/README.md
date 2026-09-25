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
