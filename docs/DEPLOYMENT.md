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

## 1. Provision the database

The schema is written for MySQL/MariaDB. Any managed MySQL server works; point
`DATABASE_URL` at it in the form

```
mysql+pymysql://USER:PASSWORD@HOST:PORT/DATABASE
```

`mysql://` and `mariadb://` URLs are rewritten to `mysql+pymysql://`
automatically, so a connection string copied from a provider's dashboard works
unchanged. Hosted MySQL options that hand out a URL like this include Aiven,
PlanetScale, Clever Cloud and a MySQL instance on any VPS.

**Render does not offer managed MySQL** (only Postgres), so its Blueprint
attaches a persistent disk and points `DATABASE_URL` at a SQLite file on that
disk:

```yaml
disk:
  name: app-data
  mountPath: /var/data
  sizeGB: 5
envVars:
  - key: DATABASE_URL
    value: sqlite:////var/data/email_orchestrator.db
```

That works out of the box and survives restarts and redeploys, but it is a
single-writer database on one instance. For production traffic, delete the
`disk` block from `render.yaml` and set `DATABASE_URL` to a real MySQL server;
the app prefers MySQL whenever `DATABASE_URL` says so.

The app creates its own tables on startup (`init_db()`), so no migration step is
needed.

## 2. Set environment variables

These are required for a public deployment. Do **not** reuse the local `.env`.

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | MySQL connection string, or the SQLite path on a persistent disk |
| `JWT_SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `LOCAL_TENANT_NAME` / `LOCAL_USER_EMAIL` | Identity of the implicit workspace |
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

### There is no login — put access control in front of the app

The app has no sign-in screen anywhere, including this deployment. A request
without credentials is served as the single implicit workspace, so **anyone who
knows the URL can read contacts, change settings, re-enable autopilot and send
mail as the configured mailbox.**

That is acceptable only because the shipped platform files keep
`MAIL_SUPPRESS_SEND=true`, `AUTOPILOT=false` and `AUTO_APPROVE=false`: nothing is
actually delivered until you change them. Before you turn real sending on:

1. Put an authenticating proxy in front of the service (HTTP basic auth at the
   platform edge, an identity-aware proxy, or a VPN), or
2. Keep the service unexposed and reach it only from your own machine.

Do not enable `AUTOPILOT`/`AUTO_APPROVE` or `MAIL_SUPPRESS_SEND=false` on a public
URL that has no access control in front of it.

Treat any SMTP credentials that were reachable this way as compromised: the
deployed instance exposed a working Gmail account (host, user and sender were
readable anonymously) until autopilot was turned off. Rotate the mailbox's app
password and re-enter it in **Settings** once access control is in place.

## 3. Deploy

Railway:

```bash
npm i -g @railway/cli
railway login
railway init
railway add --plugin mysql   # provides DATABASE_URL for the service
railway variables --set JWT_SECRET_KEY=...
railway up
railway domain
```

Railway has no persistent disk by default, so the SQLite fallback writes to an
ephemeral filesystem and is wiped on every deploy. Always add a MySQL plugin or
set `DATABASE_URL` to an external MySQL server before pointing real traffic at
it; the app logs an explicit warning when it starts on SQLite on a hosted
platform.

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
the dashboard is compiled before uvicorn starts. `node` and `npm` are part of
Render's native build environment, so the `npm` steps in `buildCommand` work
without extra setup. `PUBLIC_BASE_URL` and `CORS_ORIGINS` default to
`RENDER_EXTERNAL_URL`, which Render sets on the service itself, so tracking
links point at the deployed host with no manual edit.

### Why the first Render deploy failed

The previous deploy started with `DATABASE_URL` inherited from the local `.env`,
which addresses `localhost`. No MySQL server runs inside the instance, so
startup raised `Can't connect to MySQL server on 'localhost' (111)` and the
process exited. Two changes make that impossible now:

- `render.yaml` sets `DATABASE_URL` explicitly to the SQLite file on the mounted
  disk instead of relying on whatever the dashboard inherited.
- `app/main.py` no longer aborts when the database is unreachable. It logs the
  failure, skips schema work and background jobs, keeps serving, and `/health`
  answers `503` with `"database": {"healthy": false}` so the platform probe
  reports the real problem rather than a silent crash.

If you set a MySQL `DATABASE_URL` by hand, use the provider's internal hostname
(not `localhost`) and make sure it needs no SSH tunnel.

VPS or bare metal: follow [SAAS_GUIDE.md](SAAS_GUIDE.md) — MariaDB, a systemd
unit running uvicorn, and nginx as the reverse proxy. Run `npm run build --prefix
frontend` on the server before starting the unit so `frontend/dist` exists.

## 4. Verify

```bash
curl https://YOUR-URL/health          # {"status":"healthy",...}
curl -I https://YOUR-URL/             # 200 and the MailMatrix shell
```

`/health` returns `200` only when the database answers `SELECT 1`; a `503` means
`DATABASE_URL` is wrong, which the logs restate with the host it tried to reach
(password redacted).

Then open the deployment. There is no sign-in screen: the dashboard opens directly
on the Overview of the implicit workspace, which is provisioned on the first
request. It starts empty because a new workspace holds no sample data — only the
starter templates. **Settings** shows the deployment's `SMTP_*` values because the
implicit workspace inherits the environment; replace them with your own relay if
you want a different mailbox, and only then set `MAIL_SUPPRESS_SEND=false`.

Because the app has no authentication, anyone who finds the URL works in the same
workspace. Either keep the instance private (proxy or VPN in front of it) or gate it
at your edge; `POST /api/auth/register` and the token endpoints only matter for the
programmatic API.

## Serverless alternative

If you must run on a serverless host (Vercel, Lambda), set
`ENABLE_BACKGROUND_JOBS=false` and drive the same work from an external cron:

```bash
curl -X POST https://YOUR-URL/api/scheduling/run-now -H "Authorization: Bearer $TOKEN"
curl -X POST https://YOUR-URL/api/inbox/sync -H "Authorization: Bearer $TOKEN"
```

Pacing still applies, so a large queue will drain slowly across several cron
runs rather than in one.
