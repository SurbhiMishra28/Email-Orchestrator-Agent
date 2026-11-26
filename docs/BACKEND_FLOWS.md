# Backend Flows

How a request moves through the backend: which module handles it, what it calls,
which tables it writes and which external service it touches. This is the
implementation-level companion to [FLOWS.md](FLOWS.md), which describes the
product behaviour; here the focus is module wiring and call order.

Entry point: `app.main:app` (served locally by uvicorn, and on Vercel through the
`api/index.py` adapter). One FastAPI process serves the JSON API under `/api`,
the SPA at `/`, and `/ws/live-logs`.

## 1. Layer map

```mermaid
flowchart LR
    UI[React SPA] --> R[FastAPI routers<br/>app/routers/*]
    API[External API client] --> R
    CRON[External cron] --> R
    R --> DEP[app/deps.py<br/>auth + tenant]
    R --> SVC[app/services/*]
    R --> AG[app/agents.py]
    R --> DB[(SQLAlchemy<br/>app/db.py)]
    SVC --> AG
    SVC --> DB
    AG --> DB
    SVC --> SMTP[SMTP relay]
    SVC --> IMAP[IMAP mailbox]
    AG --> LLM[NVIDIA LLM<br/>optional]
    SVC --> WS[app/live_logs.py<br/>/ws/live-logs]
```

| Layer | Module | Responsibility |
|---|---|---|
| App / wiring | `app/main.py` | Lifespan, scheduler, rate limiter, `/api/state`, `/api/run`, analytics |
| Auth | `app/auth.py`, `app/deps.py` | JWT issue/verify, local-user fallback, `current_tenant_id` |
| Routers | `app/routers/*.py` | HTTP parsing, tenant scoping, status codes |
| Business logic | `app/services/*.py` | Limits, sending, inbox, follow-ups, outreach, usage, tracking |
| Agents | `app/agents.py` | Personalization, sending wrapper, reply analysis, auto-reply, queue |
| Data | `app/db.py` | Models, session factory, additive schema upgrades |
| Config | `app/config.py` | Environment flags (`LOCAL_*`, caps, `ENABLE_BACKGROUND_JOBS`) |

## 2. Module inventory

| Module | Called by | Talks to |
|---|---|---|
| `main.py` | uvicorn | `db`, `services/*`, `agents`, `routers/api.py` |
| `routers/api.py` | `main.py` | mounts every resource router with `Depends(get_current_user)` |
| `routers/{contacts,drafts,templates,smtp,settings,queue,replies,verifications,inbox,tracking,agents,lists,tenants,scheduling,ab_tests,campaigns}.py` | `routers/api.py` | `services/*`, `agents.py`, `db` |
| `routers/auth.py` | `routers/api.py` (public) | `auth.py`, `db` |
| `routers/track.py` | `routers/api.py` (public) | `services/tracking.py` |
| `services/limits.py` | routers, `agents.QueueManager` | `db` |
| `services/mailer.py` | `agents.py`, `routers/drafts.py`, `routers/agents.py`, `routers/smtp.py` | SMTP |
| `services/inbox.py` | `main.py` scheduler, `routers/inbox.py` | IMAP, `db` |
| `services/outreach.py` | `main.py`, `routers/contacts.py` | `agents.EmailAgent`, `services/recipients` |
| `services/followups.py` | `main.py`, `routers/queue.py` | `agents.expand_template_with_ai`, `db` |
| `services/send_worker.py` | `main.py`, `routers/queue.py`, `routers/scheduling.py` | `agents.QueueManager` |
| `services/usage.py` | send paths | `db.UsageLog` |
| `services/tracking.py` | send paths, `routers/track.py` | `db`, HMAC secret from `auth.py` |
| `services/recipients.py` | every send/draft path | none (pure checks) |
| `services/provisioning.py` | startup, registration | `db` |
| `services/bounces.py` | reply pipeline | pure parsing (DSN detection) |
| `services/verification.py` | `routers/verifications.py` | DNS/SMTP probes |
| `services/abtesting.py` | `routers/ab_tests.py`, `routers/queue.py` | `db` |
| `live_logs.py` | `@instrument_agent` classes | in-memory subscriber queues |

## 3. Startup and shutdown

```mermaid
sequenceDiagram
    participant P as Process
    participant M as lifespan (main.py)
    participant D as db.py
    participant PR as services/provisioning
    participant S as AsyncIOScheduler

    P->>M: start
    M->>D: init_db() (create_all + _ensure_columns)
    alt database reachable
        M->>M: _bootstrap_database()
        M->>D: drafts with status=sending become failed, "interrupted by server restart"
        M->>PR: provision_tenant_defaults() per tenant
        alt ENABLE_BACKGROUND_JOBS
            M->>S: add inbox_poll (IMAP_POLL_MINUTES)
            M->>S: add autopilot (5 min)
            M->>S: start()
        end
    else database unreachable
        M->>M: log; keep serving, /health returns 503
    end
    P->>M: shutdown
    M->>S: shutdown(wait=False)
```

`init_db()` is additive: `Base.metadata.create_all` plus `_ensure_columns()`,
which adds `tenant_id` to legacy tables, backfills them to the first tenant,
re-creates missing columns and rescopes `UNIQUE(uid)` to `UNIQUE(tenant_id, uid)`.

Provisioning is idempotent and creates a `Settings` row, blank `SMTPConfig` and
`IMAPConfig` rows, and starter `intro` / `followup` templates. Only the implicit
workspace inherits `SMTP_*` / `IMAP_*` from the environment
(`inherit_environment=True`), which is why an extra registered tenant with no own
relay cannot send.

## 4. Request gate chain

```mermaid
flowchart TD
    A[HTTP request] --> B{Route group}
    B -- "/health, /api/auth/*, /api/track/*, /ws/live-logs" --> C[Public handler]
    B -- resource router --> D[Depends get_current_user]
    D --> E{Bearer token sent?}
    E -- no --> F[get_or_create_local_user<br/>implicit workspace]
    E -- yes --> G[decode JWT sub]
    G --> H{user exists and active?}
    H -- no --> I[401 / 403]
    H -- yes --> J[UserPayload]
    F --> K[Depends current_tenant_id]
    J --> K
    K --> L[Rate limiter key<br/>tenant:id / user:id / ip]
    L --> M{limit hit?}
    M -- yes --> N[429]
    M -- no --> O[Router handler<br/>queries filtered by tenant_id]
    O --> P[Response]
```

`routers/api.py` attaches `Depends(get_current_user)` at the router level, so a
new endpoint in an existing resource router is protected by default. The auth
router and the tracking router are mounted without that dependency on purpose.

`current_tenant_id()` rejects a payload with no tenant (403) instead of running
an unscoped query.

## 5. Dashboard read path (`GET /api/state`)

```mermaid
flowchart LR
    A["GET /api/state"] --> B[tenant_id from the token or the implicit workspace]
    B --> C[contacts, drafts, logs, tool_uses,<br/>reply events — tenant filtered]
    C --> D[_build_analytics]
    C --> E[_build_usage]
    C --> F[resolve_smtp_config / resolve_imap_config]
    D --> G[counts, reply types, 14-day series]
    E --> H[usage_logs today/month + plan limit]
    F --> I[public views, no password]
    G --> J[JSON payload]
    H --> J
    I --> J
```

Invalid rows are skipped (validation error logged) rather than failing the whole
payload, so one bad legacy record cannot blank the dashboard.

## 6. Contact import

```mermaid
sequenceDiagram
    participant C as Client
    participant R as routers/contacts.py
    participant DB as Database
    participant O as services/outreach

    C->>R: POST /api/contacts/import {csv, default_eligible}
    R->>R: parse header + rows
    loop each row
        R->>R: validate email, mailable check
        R->>DB: existing contact in tenant?
        alt new
            R->>DB: INSERT Contact
        else existing
            R->>DB: UPDATE profile fields, eligibility
        end
    end
    R->>DB: INSERT Log
    alt AUTOPILOT and AUTO_APPROVE and eligible rows
        R->>O: BackgroundTasks: send_intro_to_imported_contacts(ids, tenant)
        O->>O: create_intro_drafts(require_automation=True)
        O->>O: QueueManager.process_queue()
        O->>DB: INSERT Log
    end
    R-->>C: imported / updated / skipped / errors
```

The import route is synchronous except for the optional outreach task, which
runs after the response has been handed to the client.

## 7. Draft and send paths

Every send path ends in `services/mailer.send_email` and passes
`check_tenant_send_allowed` before it. The one wrapper that can bypass the check
is `agents.EmailAgent.run()`, which sends inline when called with
`auto_approve=True, send_via_smtp=True`; the automatic outreach path calls it with
both false so the queue owns delivery, and no route calls it that way.

```mermaid
flowchart TD
    A["POST /api/drafts/compose"] --> B[INSERT Draft status=draft]
    B --> C[record_usage emails_drafted]

    D["POST /api/drafts/{id}/send"] --> E[load contact, mailable?]
    E --> F[resolve_smtp_config]
    F --> G[check_send_allowed]
    G --> H[claim: UPDATE status=sending]
    H --> I[send_email via tracking.send_html_for_draft]
    I -- accepted --> J[status=sent, sent_at,<br/>record_usage emails_sent]
    I -- MailDeliveryError --> K[status=failed]

    AG["POST /api/agents/send"] --> AG0[recipient must be a tenant contact]
    AG0 --> AG1[INSERT Draft status=sending<br/>direct_send marker]
    AG1 --> G
    G --> AG2[send_email with caller from_name/from_email]

    L["POST /api/queue/run"] --> M[QueueManager.process_queue]
    N["POST /api/queue/run-all"] --> O[_create_drafts + drain_queue]
    P["POST /api/queue/run-async"] --> Q[SendWorker.submit runner]
    Q --> O
    O --> M

    M --> R{SMTP configured?}
    R -- no --> S[skip all, no DB mutation]
    R -- yes --> T{contact eligible,<br/>not blacklisted,<br/>address mailable?}
    T -- no --> U[fail draft + blacklist contact<br/>for placeholder addresses]
    T -- yes --> G2[check_send_allowed]
    G2 -- pacing --> V[paused, break pass]
    G2 -- cap --> W[skipped]
    G2 -- allowed --> X[claim status=sending]
    X --> Y[send_email]
    Y -- accepted --> Z[status=sent, usage,<br/>auto_reply_sent event]
    Y -- error --> AA[status=failed,<br/>auto_reply_failed event]
```

`services/limits.py` is the single gate:

```mermaid
flowchart LR
    A[check_tenant_send_allowed] --> B["effective daily = min(DAILY_CAP, Settings.daily_cap, plan daily_email_limit)"]
    B --> C{today >= effective?}
    C -- yes --> D[block: plan or daily cap]
    C -- no --> E{domain count >= domain_cap?}
    E -- yes --> F[block: domain cap]
    E -- no --> G{seconds since last send < 60?}
    G -- yes --> H[block: pacing]
    G -- no --> I[allow]
```

Warm-up ramp: days 1–3 → 5/day, 4–7 → 10, 8–14 → 30, then 50. A blocked check
never mutates the draft; the queue treats `Pacing` as "stop this pass" and any
other reason as "skip this draft".

Every draft is claimed with a conditional `UPDATE ... WHERE status IN
('draft','blocked')` before SMTP runs, so two concurrent senders cannot deliver
the same row.

## 8. Async send worker

```mermaid
stateDiagram-v2
    [*] --> pending: submit(tenant_id)
    pending --> running: semaphore acquired
    running --> complete: drain_queue returned
    running --> failed: exception
    complete --> [*]
    failed --> [*]
```

`SendWorker` bounds concurrency with `SEND_CONCURRENCY` (default 2) and keeps at
most 200 jobs, evicting finished ones. Jobs live in process memory, so a restart
forgets them; `GET /api/queue/jobs/{id}` returns 404 for another tenant's id.

`drain_queue()` calls `process_queue` repeatedly (max 200 passes, 1800 s) and
sleeps out the 60-second pacing gap between passes, so one click delivers the
whole batch while every individual send still passes `check_send_allowed`.

`/api/queue/run-all` drains inline for at most `SYNC_DRAIN_SECONDS` (25 s) when
background jobs are enabled, then hands the remainder to the worker. With
`ENABLE_BACKGROUND_JOBS=false` it drains inline for the full bound instead,
because a handoff to a worker that will not survive the request would drop those
sends.

## 9. Reply and bounce pipeline

Driven by `_process_incoming_replies()` in `main.py`, called from the autopilot
pass and from `POST /api/scheduling/run-now`.

```mermaid
flowchart TD
    A[InboxMessage processed=False<br/>oldest first, limit 100] --> B{uid present?}
    B -- no --> Z[skip]
    B -- yes --> C{sender address parsed?}
    C -- no --> Z
    C -- yes --> D{DSN bounce?}
    D -- yes --> E["_record_bounce: blacklist contact,<br/>fail open drafts, campaign.bounced += 1"]
    D -- no --> F{unattended sender?<br/>no-reply, postmaster...}
    F -- yes --> Z
    F -- no --> G{contact in same tenant?}
    G -- no --> Z
    G -- yes --> H{already in ReplyProcessed?}
    H -- yes --> Z
    H -- no --> I[ReplyAnalyzerAgent.analyze_reply<br/>record_usage_metric=False]
    I --> J[INSERT ReplyProcessed<br/>record_usage replies_received]
    J --> K[AutoResponder.generate_response]
    K --> L{template for reply type?}
    L -- no --> M[classification stored only]
    L -- yes --> N[send_response: INSERT Draft<br/>message_kind=auto_reply]
    N --> O[autopilot queue pass sends it]
```

Bounce detection requires a daemon-style sender *and* a DSN marker
(`services/bounces.py`), so a prospect writing "it bounced" is not treated as a
delivery failure. Marking happens before contact matching, because the contact a
bounce matters for is the address named inside the report, not its sender.

## 10. Follow-up pass

`services/followups.generate_followups()` creates drafts only; sending is the
queue's job.

```mermaid
flowchart TD
    A[sent drafts with sent_at] --> B{days since send}
    B -- 3-4 --> C[stage 3]
    B -- 5-7 --> D[stage 5]
    B -- other --> E[skip]
    C --> F{replied since send?}
    D --> F
    F -- yes --> E
    F -- no --> G{already queued for this<br/>original + stage?}
    G -- yes --> E
    G -- no --> H{stage 5 while stage 3<br/>still unsent?}
    H -- yes --> E
    H -- no --> I[INSERT Draft<br/>variables.followup_for + followup_stage]
```

The pass is per tenant; called without a `tenant_id` it sweeps every tenant
separately. `FOLLOWUPS_ENABLED=false` removes the stage from the autopilot pass
entirely.

## 11. Scheduling jobs

| Job | Interval | Entry point | Work |
|---|---|---|---|
| `inbox_poll` | `IMAP_POLL_MINUTES` (min 1) | `main._poll_inbox_job` | `sync_inbox(25, tenant)` per tenant with a resolvable mailbox |
| `autopilot` | 5 min | `main._autopilot_job` | Per tenant opted into `AUTOPILOT` + `AUTO_APPROVE`: draft intros, sync inbox, answer replies, queue follow-ups, drain queue |

Both use `max_instances=1` and `coalesce=True`. Off-request triggering is
`POST /api/scheduling/run-now`, which runs the same `_autopilot_pass` and hands
sending to the worker; `POST /api/run` and `POST /api/queue/run-async` are the
other manual triggers.

Autopilot is skipped when `ENABLE_BACKGROUND_JOBS=false` (serverless), leaving
the same work reachable through the routes above and an external cron.

## 12. Tracking endpoints

```mermaid
sequenceDiagram
    participant MC as Mail client
    participant T as routers/track.py
    participant S as services/tracking
    participant DB as Database

    MC->>T: GET /api/track/open/{token}
    T->>S: record_open(token)
    S->>S: verify HMAC, decode draft:tenant
    S->>DB: INSERT Event email_opened
    T-->>MC: 1x1 GIF, no-store

    MC->>T: GET /api/track/click/{token}?url=
    T->>S: record_click(token, url)
    S->>S: verify HMAC, validate http(s) target
    S->>DB: INSERT Event link_clicked
    T-->>MC: 302 to target (or base URL)
```

These are public by design; the signed token is the credential. Tracking is off
unless `Settings.tracking_enabled` is true for the tenant, and auto-reply drafts
are never tracked.

## 13. Where state is written

| Action | Tables written |
|---|---|
| Register / first local run | `tenants`, `users`, `tenant_members`, `settings`, `smtp_config`, `imap_config`, `templates` |
| Contact import | `contacts`, `logs` (plus `drafts` when outreach runs) |
| Compose / redraft | `drafts`, `usage_logs`, `logs` |
| Manual send | `drafts` (status, sent_at, error_message, attempt_count), `usage_logs`, `logs`, optional `events` |
| Queue pass | `drafts`, `usage_logs`, `logs`, `events` (auto-reply outcomes) |
| Inbox sync | `inbox_messages`, `logs` |
| Reply processing | `inbox_messages.processed`, `replies_processed`, `events`, `usage_logs`, `drafts` |
| Bounce handling | `contacts` (blacklist), `drafts` (failed), `campaigns.bounced`, `logs` |
| Follow-ups | `drafts`, `logs` |
| Open / click | `events` |
| Settings / SMTP / IMAP | `settings`, `smtp_config`, `imap_config`, `logs` |

Every tenant-owned table carries `tenant_id` and every router query filters on it.
The exceptions are the platform tables: `tenants` is the tenant itself, `api_keys`
belongs to a user (whose row carries the tenant), and `usage_logs` is keyed by
`tenant_id` but is written only through `services/usage.py`.

## 14. Error mapping

| Condition | Behaviour |
|---|---|
| Missing/invalid JWT | 401 |
| Deactivated user, user without tenant | 403 |
| Cross-tenant id (contact, draft, list, campaign, job) | 404 |
| SMTP not configured | Draft `blocked`, endpoint 409 / 503 |
| Recipient not eligible or blacklisted | Draft `blocked`, endpoint 409 / 400 |
| Address that can never receive mail | Draft `blocked`/`failed`, endpoint 422, contact blacklisted |
| Daily/plan/domain cap or pacing | 429 for direct send; `skipped`/`paused` in a queue pass |
| Relay rejected the message | Draft `failed` with `error_message`, endpoint 502 / 400 |
| IMAP not configured / unreachable | 400 / 502 on sync routes |
| Rate limiter (per tenant) | 429 |

A draft is only ever marked `sent` after the relay accepted the message, and a
failed send keeps its reason in `error_message` so it is not retried silently.

## 15. Live agent stream

`@instrument_agent` wraps every public method of the agent classes and publishes
`started` / `completed` / `failed` events to `live_logs`. `GET /ws/live-logs`
subscribes an asyncio queue per client. `_outcome()` treats a `(False, reason)`
tuple or `{"success": False}` as `failed`, so a refused send is not reported as a
successful completion. Events are transient: nothing is persisted for this
stream, and reconnecting clients miss what they were not connected for.
