# Deploying to Vercel (Neon Postgres + Gmail SMTP)

This guide deploys the app to Vercel with:

- **Frontend** built by Vite and served from Vercel's CDN.
- **API** as a single Python function (`api/index.py`).
- **Database** on Neon (Postgres). MySQL still works for local development.
- **Sending** over Gmail SMTP on port 587.
- **Scheduling** driven by cron-job.org calling `POST /api/cron/tick`.

> Vercel's Hobby plan is licensed for personal, non-commercial use. This is a
> business tool, so a Pro plan is the compliant target. Hobby is also limited to
> **one cron invocation per day**, which is why Vercel's own cron cannot drive
> the send queue here.

## 1. Provision the database (Neon)

1. Create a Neon project and copy the **pooled** connection string. The host
   contains `-pooler`, which is the endpoint that multiplexes connections and is
   the right one for serverless functions.
2. The app normalises the scheme and adds TLS for you:

   ```
   postgres://...        -> postgresql+psycopg://...&sslmode=require
   postgresql://...      -> postgresql+psycopg://...&sslmode=require
   ```

3. Create the schema once, from your machine or CI:

   ```bash
   DATABASE_URL="postgresql://USER:PASSWORD@HOST/DB?sslmode=require" \
     python scripts/init_db.py
   ```

   This is idempotent: tables are created if missing, additive columns are added
   for older revisions, and the implicit workspace is provisioned once.

## 2. Create the Vercel project

1. Import the Git repository.
2. Vercel reads `vercel.json`:
   - `buildCommand`: `npm run build --prefix frontend`
   - `outputDirectory`: `frontend/dist`
   - `functions.api/index.py`: `maxDuration: 60`, `includeFiles: app/**`
3. `.python-version` pins Python 3.12.

## 3. Environment variables

Set these in the Vercel project settings (Production and Preview).

| Variable | Value |
|---|---|
| `DATABASE_URL` | Neon pooled Postgres URL |
| `ENABLE_BACKGROUND_JOBS` | `false` |
| `AUTO_INIT_DB` | `false` |
| `ENABLE_LIVE_LOGS` | `false` |
| `MAIL_TRANSPORT` | `smtp` |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | your Gmail address |
| `SMTP_PASS` | Gmail **app password** (not the account password) |
| `SMTP_FROM` | your Gmail address |
| `SENDER_NAME` | display name shown to recipients |
| `IMAP_HOST` / `IMAP_PORT` / `IMAP_USER` / `IMAP_PASS` | for inbox sync |
| `NVIDIA_API_KEY` / `NVIDIA_MODEL` | AI personalisation (optional) |
| `BASIC_AUTH_USER` / `BASIC_AUTH_PASSWORD` | dashboard access gate |
| `CRON_SECRET` | shared secret for the cron route |
| `PUBLIC_BASE_URL` | leave unset; Vercel's URL is detected automatically |

Do **not** set `MAIL_SUPPRESS_SEND=true` in production — that turns every send
into a no-op that reports success.

### Why `ENABLE_BACKGROUND_JOBS=false`

Vercel freezes the function as soon as it responds. APScheduler would never fire,
and a background send task would be abandoned mid-handshake. With this flag off:

- the inbox and autopilot run only when the cron route is called;
- queue-draining endpoints drain a **bounded** window inline and report what is
  left (`paused` / `remaining`) instead of handing off to a worker that does not
  exist.

## 4. Access control

The app has no login screen, so the Basic auth gate is what protects a public
URL. Every route requires credentials except:

- `/health`
- `/api/track/open/{token}` and `/api/track/click/{token}` — fetched by
  recipients' mail clients and browsers
- `/api/cron/*` — authenticated by `CRON_SECRET`

The browser prompts once and then sends the credentials automatically.

## 5. Scheduling (cron-job.org)

1. Create a free account at cron-job.org.
2. Add a job:
   - **URL**: `https://YOUR-APP.vercel.app/api/cron/tick`
   - **Schedule**: every 1 minute
   - **Request method**: `POST`
   - **Header**: `X-Cron-Secret: <the CRON_SECRET value>`
3. One tick polls the inbox, answers replies, drafts follow-ups and drains the
   queue for a bounded window. Pacing allows one email per 60 seconds, so the
   throughput ceiling is roughly one message per minute per workspace.

The route is disabled (404) while `CRON_SECRET` is unset, and answers 401 to a
wrong secret, so an empty variable can never leave the pipeline open.

## 6. Verify the deployment

```bash
APP=https://YOUR-APP.vercel.app

# 1. Protected API answers 401 without credentials
curl -s -o /dev/null -w "%{http_code}\n" "$APP/api/state"          # 401

# 2. ...and 200 with them
curl -s -u "$BASIC_AUTH_USER:$BASIC_AUTH_PASSWORD" "$APP/api/state"

# 3. Tracking links stay public (no credentials)
curl -s -o /dev/null -w "%{http_code}\n" "$APP/api/track/open/test" # 200 or 404

# 4. Cron route rejects a wrong secret
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$APP/api/cron/tick" \
  -H "X-Cron-Secret: wrong"                                        # 401

# 5. ...and accepts the right one
curl -s -X POST "$APP/api/cron/tick" -H "X-Cron-Secret: $CRON_SECRET"
```

Then in the dashboard: **Settings → SMTP** → Test, followed by a single send to
your own address, and confirm the message arrives.

## 7. Sending behaviour on Vercel

- **Port 25 is blocked outbound; 465 and 587 are open.** Gmail submission on 587
  with STARTTLS works.
- The send must be awaited inside the invocation. The code already does this:
  `drain_queue` is awaited before the response is returned.
- Function bundle limit for Python is 500 MB uncompressed, and Hobby allows a
  300 s invocation. `maxDuration: 60` keeps a stuck drain from holding a minute
  of compute.
- Gmail free accounts allow roughly 500 recipients per day, and Google's terms
  prohibit unsolicited bulk mail. High-volume sending from a consumer mailbox
  risks throttling or suspension; a dedicated transactional provider with a
  verified domain is the durable answer.

## 8. Local development (MySQL)

Local runs are unchanged and still use MySQL plus APScheduler:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`AUTO_INIT_DB` defaults to `true`, so the schema is created on first boot. The
test suite uses a throwaway MySQL database and sets `MAIL_SUPPRESS_SEND=true`.

## 9. Notes and trade-offs

- **`VERCEL_URL` is a host without a scheme.** `app/config.py` prefixes it with
  `https://` and prefers `VERCEL_PROJECT_PRODUCTION_URL` so preview deployments
  do not poison tracking links.
- **Live logs are disabled.** `/ws/live-logs` needs a long-lived connection; the
  dashboard renders the panel as unavailable instead of reconnecting forever.
- **Rewrites preserve the original path.** `vercel.json` sends `/api/*` and
  `/health` to the function while assets and `/index.html` come from the CDN.
  If a deployment ever routes `/api/...` to `/api/index` literally, switch to the
  legacy `routes` form.
- **`AUTO_INIT_DB=false` means schema changes are manual.** Run
  `scripts/init_db.py` after upgrading; it is additive and safe to repeat.