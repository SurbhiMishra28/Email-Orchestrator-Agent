# Deploying to Railway, Render, or Fly.io

All three configs in the repo root target the same `Dockerfile`:

| Platform | Config file | Notes |
|----------|-------------|-------|
| Railway | `railway.toml` | Dockerfile builder, healthcheck on `/health` |
| Render | `render.yaml` | Blueprint; `runtime: docker` |
| Fly.io | `fly.toml` | Replace `app = "email-orchestrator"` with your own name |

## Why a long-lived container, not a serverless function

`ENABLE_BACKGROUND_JOBS=true` starts APScheduler, which drives IMAP inbox
polling (every `IMAP_POLL_MINUTES`) and the autopilot pass (every 5 minutes).
The send worker also keeps a thread between requests so it can honour the
60-second pacing rule in `app/services/limits.py`. A platform that freezes the
process between requests loses both. All three configs above therefore run a
persistent container with at least one instance always on.

## 1. Provision MySQL

Railway, Render and Fly all offer managed MySQL. Create the database first and
copy its connection string; it becomes `DATABASE_URL` in the form

```
mysql+pymysql://USER:PASSWORD@HOST:PORT/DATABASE
```

The app creates its own tables on startup (`init_db()`), so no migration step
is needed.

## 2. Set environment variables

These are required for a public deployment. Do **not** reuse the local `.env`.

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | Managed MySQL connection string |
| `JWT_SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `SINGLE_USER_MODE` | `false` — otherwise every visitor shares one workspace |
| `PUBLIC_BASE_URL` | Your deployed https URL (used for tracking pixel/click links) |
| `CORS_ORIGINS` | Your deployed origin only |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` or your preference |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `SMTP_FROM` | Sending mailbox |
| `IMAP_HOST` / `IMAP_PORT` / `IMAP_USER` / `IMAP_PASS` | Reply sync (read-only) |
| `NVIDIA_API_KEY` | Optional; without it built-in templates are used |
| `MAIL_SUPPRESS_SEND` | `true` until you have verified sending |
| `AUTOPILOT` / `AUTO_APPROVE` | `false` until you intentionally want unattended sending |

The platform files set the safety defaults (`MAIL_SUPPRESS_SEND=true`,
`AUTOPILOT=false`, `AUTO_APPROVE=false`) so a deploy cannot start mailing people
before you have checked it.

## 3. Deploy

Railway:

```bash
npm i -g @railway/cli
railway login
railway init
railway up
railway domain
```

Render:

```bash
# Push the repo, then in the dashboard: New > Blueprint > select this repo.
# render.yaml is picked up automatically.
```

Fly.io:

```bash
# Install: https://fly.io/docs/hands-on/install-flyctl/
fly auth login
fly launch --no-deploy      # keep the existing fly.toml
fly secrets set DATABASE_URL="mysql+pymysql://..." JWT_SECRET_KEY="..." \
  SINGLE_USER_MODE=false PUBLIC_BASE_URL="https://<app>.fly.dev" \
  CORS_ORIGINS="https://<app>.fly.dev" SMTP_HOST="..." SMTP_USER="..." SMTP_PASS="..." \
  SMTP_FROM="..."
fly deploy
```

## 4. Verify

```bash
curl https://YOUR-URL/health          # {"status":"healthy",...}
curl -I https://YOUR-URL/             # 200 and the MailMatrix shell
```

Then open the dashboard, register an account, and confirm the Overview loads.
Only after that should you set `MAIL_SUPPRESS_SEND=false` and add real SMTP
credentials.

## Serverless alternative

If you must run on a serverless host (Vercel, Lambda), set
`ENABLE_BACKGROUND_JOBS=false` and drive the same work from an external cron:

```bash
curl -X POST https://YOUR-URL/api/scheduling/run-now -H "Authorization: Bearer $TOKEN"
curl -X POST https://YOUR-URL/api/inbox/sync
```

Pacing still applies, so a large queue will drain slowly across several cron
runs rather than in one.
