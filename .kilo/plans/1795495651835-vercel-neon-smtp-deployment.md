# Vercel + Neon Postgres + Gmail SMTP Deployment Plan

## Context

Audit of `email-orchestrator` against the target: deploy to Vercel, send over SMTP, keep scheduling working, tidy the folder layout.

### What already works (verified against live credentials)

- Gmail SMTP login and IMAP login both succeed on `smtp.gmail.com:587` / `imap.gmail.com:993` with the app password in `.env`.
- NVIDIA key is valid; `NVIDIA_MODEL=nvidia/nemotron-3.5-super-vl-120b-a12b` responds through `ChatNVIDIA`.
- `MAIL_TRANSPORT=smtp` is already set in `.env`, so the broken Resend path (unverified domain, 403) is bypassed.
- `/api/cron/tick` and `/api/cron/status` exist, are secret-gated, and drain per-tenant.
- `tests/` is green: 198 passed.

### Vercel blockers found in code

| # | Finding | Location |
|---|---|---|
| 1 | No `vercel.json`; no `api/` entrypoint. Root `main.py` is a bare `app.main:app` re-export with no Vercel wiring. | `main.py` |
| 2 | `HOSTED_PLATFORM` does not include `VERCEL`, so a loopback `DATABASE_URL` is not detected and the SQLite fallback warning never fires. | `app/db.py:57` |
| 3 | No `postgres`/`psycopg` support. `_DIALECT_ALIASES` covers MySQL only; `pymysql` is the only driver. | `app/db.py:31-40` |
| 4 | `_platform_public_url()` does not read `VERCEL_URL`, so tracking links and CORS would fall back to `http://localhost:8000`. | `app/config.py:19-34` |
| 5 | `app.mount("/", SPAStaticFiles(...))` at import time means the function would serve the SPA; incompatible with static-on-CDN serving and blows up the bundle. | `app/main.py:1139-1143` |
| 6 | `POST /api/run` always hands off to `get_worker().submit()`; the asyncio task dies when the function responds. | `app/main.py:1091-1095` |
| 7 | `POST /api/scheduling/run-now` same background-worker handoff. | `app/routers/scheduling.py:185` |
| 8 | `POST /api/queue/run-all` with `ENABLE_BACKGROUND_JOBS=false` drains **unbounded** (`drain_queue(tenant_id=tenant_id)`), so the function runs until Vercel kills it at `maxDuration`. | `app/routers/queue.py:202-206` |
| 9 | `POST /api/queue/send/{contact_id}` also uses `get_worker()` unconditionally. | `app/routers/queue.py:355` |
| 10 | WebSocket `/ws/live-logs` cannot work on Vercel (no WS upgrade for Python functions). Frontend retries forever every ≤30 s. | `app/main.py:1032`, `frontend/src/App.jsx:267-301` |
| 11 | No authentication anywhere. A public URL exposes contacts, settings and sending. | `app/auth.py`, `app/deps.py` |
| 12 | `init_db()` + `_bootstrap_database()` run on every startup (DDL + tenant provisioning). On serverless that means every cold start issues schema checks to Neon. | `app/main.py:502-511`, `app/db.py:707` |
| 13 | `app/main.py` imports `apscheduler` at module scope and starts it by default (`ENABLE_BACKGROUND_JOBS` defaults to `true`). | `app/main.py:9,518` |

### Verified platform facts (Vercel docs, Nov 2026)

- Port 25 blocked outbound; **465 and 587 open** → Gmail SMTP over 587 works.
- "Once a function sends its response, background work pauses" → all sends must be awaited inline.
- Python function bundle: 250 MB uncompressed standard, **500 MB for Python**. Hobby `maxDuration` default/max 300 s with Fluid compute.
- **Hobby cron runs at most once per day** (deploy-time error otherwise). App pacing is 60 s/email and inbox poll is 10 min → Vercel Cron is unusable on Hobby.
- Hobby is licensed for non-commercial use only; this is a business tool (see Risks).

### Decisions taken

1. **Database: Neon Postgres.** Add `psycopg` + a `postgresql://` dialect alias. Keep MySQL working for local dev (dual-dialect).
2. **Access control: HTTP Basic auth middleware inside the app.** Exempt `/health`, `/api/track/*`, `/api/cron/*`.
3. **Serving: static frontend from Vercel CDN + one Python function for `/api/*`.** Guard the `StaticFiles` mount so it is skipped on Vercel.
4. **Scheduler: cron-job.org → `POST /api/cron/tick`** with `X-Cron-Secret`, every minute.

### Target folder structure

```
/
├── api/
│   └── index.py              # NEW: Vercel Python entrypoint (re-exports app.main:app)
├── app/                      # unchanged package layout
│   ├── config.py             # + VERCEL_URL, BASIC_AUTH_*, AUTO_INIT_DB, POSTGRES alias
│   ├── db.py                 # + postgres dialect, pool tuning, dialect-aware DDL
│   ├── main.py               # + basic-auth middleware, - static mount on Vercel, + gated jobs
│   ├── security.py           # NEW: basic-auth middleware
│   ├── routers/              # + cron.py (exists)
│   └── services/
├── frontend/                 # unchanged (Vite app)
├── scripts/
│   ├── get_gmail_refresh_token.py
│   ├── init_db.py            # NEW: one-time Neon schema bootstrap
│   └── init_templates.py     # MOVED from root
├── tests/
├── docs/
│   ├── DEPLOYMENT.md         # rewritten: Vercel + Neon + cron-job.org
│   ├── SETUP_GUIDE.md
│   ├── QUICKSTART.md
│   ├── ROADMAP.md
│   ├── reference/
│   └── legacy/               # render.yaml, railway.toml moved here
├── vercel.json               # NEW
├── .python-version           # NEW: 3.12
├── requirements.txt          # + psycopg[binary]
├── requirements-dev.txt
├── pytest.ini
├── package.json
├── .env.example
└── .gitignore
```

Removed from root: `main.py` (Vercel shim, replaced by `api/index.py`), `email-templates.txt` (unreferenced anywhere in code).

---

## Tasks

### Task 1 — Postgres support in `app/db.py`

- Extend `_DIALECT_ALIASES` (`app/db.py:31`) with:
  - `"postgres://": "postgresql+psycopg://"`
  - `"postgresql://": "postgresql+psycopg://"`
- Add `psycopg[binary]>=3.1` to `requirements.txt`.
- Make the legacy DDL dialect-aware (only runs on pre-existing MySQL DBs; a fresh Neon DB skips all of it because every block is guarded by `if col not in columns`):
  - `_ensure_uid_uniqueness` line 1024: `ALTER TABLE ... DROP INDEX` is MySQL-only → use `DROP INDEX` for `postgresql`.
  - line 820: `BOOLEAN DEFAULT 0` → `BOOLEAN DEFAULT FALSE` on Postgres.
  - line 837: `DATETIME NULL` → `TIMESTAMP NULL` on Postgres.
  - line 905-909: `tags JSONB DEFAULT '[]'` → `DEFAULT '[]'::jsonb` on Postgres.
  - line 846-855 (`CREATE TABLE replies_processed ... AUTOINCREMENT`) → only reachable if `create_all` failed; add a `SERIAL`/`GENERATED BY DEFAULT` variant or skip on Postgres.
- Pool tuning for serverless (many concurrent instances): use `pool_size=1`, `max_overflow=5`, `pool_recycle=1800` when the URL is Postgres; keep `pool_pre_ping=True`.
- Require TLS: append `?sslmode=require` when the URL is Postgres and has no `sslmode` already.

**Validate:** `DATABASE_URL=postgresql://... python -c "from app.db import engine; print(engine.dialect.name)"` → `postgresql`. Then `init_db()` against Neon creates all 25 tables.

### Task 2 — Vercel platform detection

- `app/config.py:11-34`: add first-priority branch reading `VERCEL_PROJECT_PRODUCTION_URL` (fallback `VERCEL_URL`), prefixed with `https://`. This fixes tracking pixel/click links and CORS automatically.
- `app/config.py`: add
  - `BASIC_AUTH_USER: str = os.getenv("BASIC_AUTH_USER", "")`
  - `BASIC_AUTH_PASSWORD: str = os.getenv("BASIC_AUTH_PASSWORD", "")`
  - `AUTO_INIT_DB: bool = os.getenv("AUTO_INIT_DB", "true").lower() == "true"`
  - `ENABLE_LIVE_LOGS: bool = os.getenv("ENABLE_LIVE_LOGS", "true").lower() == "true"`
- `app/db.py:57`: add `or os.getenv("VERCEL")` to `HOSTED_PLATFORM`.

### Task 3 — HTTP Basic auth (`app/security.py`, wired in `app/main.py`)

- New middleware, enabled only when both `BASIC_AUTH_USER` and `BASIC_AUTH_PASSWORD` are non-empty; otherwise a no-op (so local dev and tests are unaffected).
- Constant-time compare via `hmac.compare_digest` on user and password.
- **Exempt paths (must stay reachable without credentials):**
  - `/health`, `/health/`
  - `/api/track/open/*`, `/api/track/click/*` — hit by recipient mail clients
  - `/api/cron/*` — authenticated by `X-Cron-Secret`
  - `/docs`, `/openapi.json`, `/redoc` (optional)
- Return `401` with `WWW-Authenticate: Basic realm="Email Orchestrator"`.
- Register with `@app.middleware("http")` before the rate limiter.
- WebSocket `/ws/live-logs`: since browsers do not send Basic credentials on WS upgrade, gate the route with `ENABLE_LIVE_LOGS` and skip registration when false.

**Validate:** `tests/test_security.py` — no creds → 401; correct creds → 200; `/health` → 200 without creds; `/api/track/open/x` → 200 without creds; wrong creds → 401.

### Task 4 — Serverless-safe job execution

- `app/main.py:1089-1095` (`POST /api/run`): when `ENABLE_BACKGROUND_JOBS` is false, drain inline with a bound, mirroring `queue.py`:
  `result["send"] = await drain_queue(tenant_id=tenant_id, max_seconds=app_settings.SYNC_DRAIN_SECONDS)` and omit `queued`/`job_id`.
- `app/routers/scheduling.py:181-187`: same change.
- `app/routers/queue.py:202-206`: bound the else-branch to `SYNC_DRAIN_SECONDS` instead of draining unbounded; keep reporting `remaining`.
- `app/routers/queue.py:355`: wrap the worker handoff in `if app_settings.ENABLE_BACKGROUND_JOBS`, otherwise run the runner inline.
- `app/config.py`: `SYNC_DRAIN_SECONDS` already exists in `app/routers/queue.py` — hoist to config if it is needed in three modules.

**Validate:** with `ENABLE_BACKGROUND_JOBS=false`, `POST /api/queue/run-all` returns within ~25 s with `paused/remaining` set; nothing is silently dropped.

### Task 5 — Live logs gating

- `app/main.py`: register `/ws/live-logs` only when `ENABLE_LIVE_LOGS` is true; return 404 otherwise.
- Add `"live_logs": app_settings.ENABLE_LIVE_LOGS` to the `/api/state` payload (`app/main.py:1015`).
- `frontend/src/App.jsx:267-301`: skip opening the socket when `live_logs` is false and render the panel as "live logs unavailable on this host" instead of reconnecting forever.

**Validate:** `/api/state` reports the flag; the browser makes no WS connection when false.

### Task 6 — Vercel entrypoint and config

- New `api/index.py`:
  ```python
  from app.main import app  # noqa: F401
  ```
- New `.python-version` containing `3.12`.
- New `vercel.json`:
  ```json
  {
    "$schema": "https://openapi.vercel.sh/vercel.json",
    "buildCommand": "npm run build --prefix frontend",
    "outputDirectory": "frontend/dist",
    "functions": {
      "api/index.py": { "maxDuration": 60, "includeFiles": "app/**" }
    },
    "rewrites": [
      { "source": "/api", "destination": "/api/index" },
      { "source": "/api/:path*", "destination": "/api/index" },
      { "source": "/health", "destination": "/api/index" },
      { "source": "/:path*", "destination": "/index.html" }
    ]
  }
  ```
  Rationale: Vercel checks the filesystem before rewrites, so `/assets/*` and `/index.html` are served from the CDN; everything else lands on the function with the original path intact. The SPA-fallback rewrite is last so it cannot swallow `/api/*`.
- `app/main.py:1139-1143`: skip the `StaticFiles` mount when `os.getenv("VERCEL")` is set (dist is not in the function bundle and must not be).
- Delete root `main.py`; update `package.json` (`start` still uses uvicorn, `build` unchanged).

**Validate:** `vercel dev` → `/` serves the SPA from `frontend/dist`, `/api/state` reaches FastAPI.

### Task 7 — One-time DB bootstrap

- `app/main.py:502-511`: wrap `_bootstrap_database()` in `if app_settings.AUTO_INIT_DB:`. Log a clear line when skipped.
- New `scripts/init_db.py`: calls `init_db()` + `_bootstrap_database()` once, prints the resolved (masked) URL, exits non-zero on failure. This is what the operator runs against Neon before the first deploy.
- Move root `init_templates.py` → `scripts/init_templates.py`.

**Validate:** with `AUTO_INIT_DB=false`, a cold start issues no DDL (check Neon's query log / `pg_stat_activity` stays quiet).

### Task 8 — Folder reorganisation

- `git mv init_templates.py scripts/init_templates.py`
- `git mv docs/DEPLOYMENT.md docs/legacy/render.yaml` — actually move `render.yaml` and `railway.toml` into `docs/legacy/`.
- Delete `email-templates.txt` (unreferenced).
- Confirm `frontend/dist` stays committed as a local fallback; Vercel rebuilds it anyway.

**Validate:** `pytest -q` still 198+ passed; `npm run build` succeeds; no import path breaks.

### Task 9 — Env vars and docs

`.env.example`: document the Vercel block —
`DATABASE_URL` (Neon, `?sslmode=require`), `VERCEL`-derived public URL, `ENABLE_BACKGROUND_JOBS=false`, `AUTO_INIT_DB=false`, `ENABLE_LIVE_LOGS=false`, `BASIC_AUTH_USER`, `BASIC_AUTH_PASSWORD`, `CRON_SECRET`, `CRON_MAX_SECONDS`, `MAIL_TRANSPORT=smtp`, SMTP/IMAP values.

`docs/DEPLOYMENT.md`: replace the Render/Railway guide with: Neon provisioning → `scripts/init_db.py` → Vercel import → env vars → cron-job.org setup → verification steps → Gmail sending limits.

### Task 10 — Tests

Add:
- `tests/test_security.py` (basic-auth middleware + exemptions).
- `tests/test_db_dialect.py` (postgres alias rewrite; `HOSTED_PLATFORM` on `VERCEL`).
- `tests/test_vercel_jobs.py` (`ENABLE_BACKGROUND_JOBS=false` → run endpoints do not call `get_worker`, and drain is bounded).
- Update `tests/test_cron_and_transport.py::test_cron_status_requires_the_secret` if the payload shape changes.

Keep the suite running against local MySQL (default `TEST_DATABASE_URL`); add an opt-in Postgres run gated on an env var.

### Task 11 — Deploy and verify

1. Neon: create project, copy the **pooled** connection string.
2. Vercel: import repo → set env vars (all from `.env.example`, secrets as-is) → deploy.
3. `curl -s -o /dev/null -w "%{http_code}" https://<app>.vercel.app/api/state` → `401`.
4. With Basic creds → `200`.
5. `curl -s https://<app>.vercel.app/api/track/open/<token>` → `200` image/gif, no credentials.
6. `POST /api/smtp/test` with creds → `{"ok": true, "transport": "smtp"}`.
7. `POST /api/cron/tick` with `X-Cron-Secret` → `200`, `{"inbox":"ok", "transport":"smtp"}`; wrong secret → `401`.
8. `POST /api/agents/send` to your own address; confirm receipt in Gmail.
9. cron-job.org: URL `https://<app>.vercel.app/api/cron/tick`, header `X-Cron-Secret: <secret>`, every 1 minute; confirm 200s in its log.

---

## Risks

1. **Vercel Hobby is non-commercial.** This is a business tool for Skora Infotech; Hobby's terms limit it to personal, non-commercial use. A Pro plan is the compliant target and also unlocks per-minute Vercel Cron.
2. **Gmail SMTP + cold outreach.** Gmail free allows ~500 recipients/day and its ToS prohibits unsolicited bulk mail; sending from Vercel IPs increases the chance of throttling or account suspension. If that happens, the codebase already has a `gmail_api` transport (`app/services/google_mail.py`) that avoids raw SMTP sockets entirely, and a Resend path that needs only a verified domain.
3. **Pacing vs. function lifetime.** At 60 s/email, one 60 s tick sends ~1 email. Throughput is bounded by cron frequency, not by the app.
4. **Neon cold start + per-request DDL.** Mitigated by `AUTO_INIT_DB=false`; `pool_pre_ping` adds one round trip per checkout.
5. **Rewrite path preservation.** If the function receives `/api/index` instead of `/api/state`, switch `rewrites` to the legacy `routes` form or set `root_path`. Verify in step 3 of Task 11.
6. **Dual-dialect drift.** MySQL (local) and Postgres (prod) share the schema; the legacy DDL paths are dialect-specific. Keep the opt-in Postgres test run.

## Out of scope

- Replacing Gmail SMTP with a dedicated ESP.
- Multi-user auth / per-tenant login (Basic auth is a single shared gate).
- Removing the `langchain-nvidia-ai-endpoints` dependency (optional bundle-size optimisation only).