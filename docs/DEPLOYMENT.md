# Deploying to Railway, Render, or a VPS

There are no containers in this project. Every target runs the FastAPI process
directly on a Python runtime and builds the React dashboard as part of the build
step, because `app/main.py` mounts `frontend/dist` at `/`.

| Platform | Config file | Runtime |
|----------|-------------|---------|
| Railway | `railway.toml` | Nixpacks (Python + Node), `buildCommand` compiles the dashboard |
| Render | `render.yaml` | `runtime: python`, `buildCommand` runs `npm ci && npm run build` |
| VPS / bare metal | none | systemd + nginx; see [SAAS_GUIDE.md](SAAS_GUIDE.md) |

## Why a long-lived process, not a serverless function

`ENABLE_BACKGROUND_JOBS=true` starts APScheduler, which drives IMAP inbox
polling (every `IMAP_POLL_MINUTES`) and the autopilot pass (every 5 minutes).
The send worker also keeps a thread between requests so it can honour the
60-second pacing rule in `app/services/limits.py`. A platform that freezes the
process between requests loses both, which is why the configs above run a
persistent service with at least one instance always on.

## 1. Provision MySQL

Railway and Render both offer managed MySQL. Create the database first and copy
its connection string; it becomes `DATABASE_URL` in the form

```
mysql+pymysql://USER:PASSWORD@HOST:PORT/DATABASE
```

The app creates its own tables on startup (`init_db()`), so no migration step is
needed. A plain VPS runs MariaDB/MySQL locally instead, as described in
[SAAS_GUIDE.md](SAAS_GUIDE.md).

## 2. Set environment variables

These are required for a public deployment. Do **not** reuse the local `.env`.

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | Managed (or local) MySQL connection string |
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

`railway.toml` uses the Nixpacks builder with an explicit build command:

```toml
buildCommand = "python -m pip install -r requirements.txt && npm ci --prefix frontend && npm run build --prefix frontend"
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
```

Render:

```bash
# Push the repo, then in the dashboard: New > Blueprint > select this repo.
# render.yaml is picked up automatically.
```

`render.yaml` declares `runtime: python` with the same build/start commands, so
the dashboard is compiled before uvicorn starts. It pins `PYTHON_VERSION` and
`NODE_VERSION`; if your Render workspace does not ship Node in the native Python
image, build the dashboard once locally, commit `frontend/dist`, and drop the
`npm` steps from `buildCommand`.

VPS or bare metal: follow [SAAS_GUIDE.md](SAAS_GUIDE.md) — MariaDB, a systemd
unit running uvicorn, and nginx as the reverse proxy. Run `npm run build --prefix
frontend` on the server before starting the unit so `frontend/dist` exists.

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
