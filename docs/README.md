# Email Orchestrator Documentation

## Overview

Email Orchestrator is a multi-tenant email automation platform: contacts and lists
in, personalized drafts out, with reply handling, follow-ups, deliverability checks
and usage metering around it. One FastAPI service serves both the JSON API and the
built React dashboard.

Both surfaces are served from the same port (`http://127.0.0.1:8000` by default):
the SPA at `/`, the API under `/api`, and the OpenAPI docs at `/docs`.

### Documentation map

| Guide | What it covers |
|---|---|
| [FLOWS.md](FLOWS.md) | End-to-end request, import, send, reply, tracking and A/B flows with diagrams |
| [BACKEND_FLOWS.md](BACKEND_FLOWS.md) | Module-level backend flows: routing, service calls, state writes and error mapping |
| [FEATURES.md](FEATURES.md) | Feature inventory with implementation status and covering tests |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Module layout and design decisions |
| [API_REFERENCE.md](API_REFERENCE.md) | Detailed request/response examples |
| [AGENTS.md](AGENTS.md) | Agent classes, methods and the live activity stream |
| [SAAS_GUIDE.md](SAAS_GUIDE.md) | Multi-tenant deployment (MariaDB, systemd, nginx) |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Native deploys: Railway, Render, VPS, and serverless cron |
| [SETUP_GUIDE.md](SETUP_GUIDE.md) | Installation and configuration |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common failures and fixes |
| [SECURITY.md](SECURITY.md) | Auth model, secrets, tracking tokens |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

## Source layout

### Backend (`app/`)

| Path | Purpose |
|---|---|
| `main.py` | FastAPI app, lifespan provisioning, SPA mount, analytics, rate limiting |
| `config.py` | Settings including the `LOCAL_*` implicit-workspace identity |
| `db.py` | SQLAlchemy models and session factory |
| `auth.py` | Password hashing, JWT issue/verify, local-user provisioning |
| `deps.py` | `current_tenant_id` and auth dependencies |
| `agents.py` | Agent classes and the queue manager |
| `live_logs.py` | Agent instrumentation and the `/ws/live-logs` broadcaster |
| `routers/` | One module per resource area (see endpoint list) |
| `services/` | Business logic: limits, usage, tracking, follow-ups, verification, send worker |

### Frontend (`frontend/`)

| Path | Purpose |
|---|---|
| `src/App.jsx` | The whole dashboard: views, state, API calls |
| `src/index.css` | Tailwind layers plus the component classes (`.app-rail`, `.btn-*`, `.surface`) |
| `tailwind.config.js` | Brand and ink palettes, radii, shadows |
| `index.html` | Vite entry; fonts load non-blocking so an offline host still paints |

## UI structure

The product name shown in the interface is **MailMatrix**. Opening the app shows a
Brevo-style splash: the `MailMatrix` wordmark fills the screen with a short loading
bar, then fades into the dashboard. The splash is skipped for users who prefer
reduced motion.

There is no sign-in screen. On first load the app asks `GET /api/auth/me` for the
workspace identity; that endpoint never answers 401, because a request without a
token is served as the implicit workspace and one is provisioned on first use. The
dashboard therefore opens straight on the Overview.

Navigation is grouped, and the rail is responsive:

- **Desktop (`>= 768px`)**: persistent 228px rail with labels and badges.
- **Mobile (`< 768px`)**: the rail becomes an off-canvas drawer opened by the
  hamburger in the top bar, with a scrim, Escape-to-close, and body scroll lock.

The theme is a dark cinematic sage: a near-black `ink` ramp (`ink-50` is the page
floor `#060b09`, `ink-900` the brightest text `#f1f7f4`) with a pale sage `brand`
scale (`brand-500` = `#7fb39d`) and `card` = `#0f1815`. The `ink` ramp is inverted on
purpose, so existing `text-ink-*` / `bg-ink-*` utilities keep their meaning; primary
buttons pair `bg-brand-500` with `text-ink-50`. All accent colours flow from
`tailwind.config.js`, so retheming is a single-file change, and `index.css` carries
the component classes (`.app-rail`, `.surface`, `.data-table`, `.splash`).

| Group | Views |
|---|---|
| Workspace | Overview, Agents |
| Audience | Contacts, Templates |
| Campaigns | Campaigns, Drafts, Experiments |
| Deliverability | Inbox, Verifications |
| Operations | Automation, Team (admin only), Settings |

Deep links work: `/contacts`, `/agents`, `/campaigns`, `/experiments` and the rest
open the matching view, and the back button moves between views.

## Accounts and sessions

The app has no login. A request without a bearer token resolves to the single
implicit workspace (`LOCAL_TENANT_NAME` / `LOCAL_USER_EMAIL`), which is provisioned
on first use along with its starter templates. The dashboard calls
`GET /api/auth/me` once at startup and never stores a session.

The token endpoints remain for the programmatic API. `POST /api/auth/register`
creates an additional tenant and its first admin, `POST /api/auth/login` issues a
7-day token for it, and `POST /api/auth/refresh-token` renews one. The UI never
calls them, and API keys under `/api/auth/api-keys` are the recommended way to
authenticate scripts.

No workspace ships with sample data. Every contact, list, template, campaign and
draft in a workspace is created by its owner, and a new tenant starts empty apart
from the starter templates `provision_tenant_defaults()` installs.

Sending always uses the workspace's own relay: `provision_tenant_defaults()` copies
the deployment's `SMTP_*` environment only for the implicit workspace. Any other
tenant created through `/api/auth/register` must enter its own host, user, password
and sender under **Settings** before anything can be delivered.

## API endpoints

All routes below are tenant-scoped. No token is required: a request without
credentials is served as the implicit workspace. A bearer token (or API key) is
optional and selects its own tenant instead.

### System and state

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness plus database check (503 `degraded` when the database is unreachable) |
| GET | `/api/state` | Aggregated dashboard payload (contacts, drafts, events, logs, analytics, usage) |
| GET | `/api/usage` | Today and month counters per tenant |
| WS | `/ws/live-logs` | Live agent activity stream |

### Auth

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/register` | Create tenant and owner |
| POST | `/api/auth/login` | Obtain access token |
| POST | `/api/auth/refresh-token` | Refresh an access token |
| GET | `/api/auth/me` | Current user and tenant |
| GET / POST | `/api/auth/api-keys` | List / create API keys |
| DELETE | `/api/auth/api-keys/{api_key_id}` | Revoke an API key |

### Contacts

| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/api/contacts` | List (up to 1000) / create |
| GET / PATCH / DELETE | `/api/contacts/{contact_id}` | Read / update / delete |
| POST | `/api/contacts/import` | CSV import with upsert (`{csv: "...", default_eligible: true}`) |
| DELETE | `/api/contacts/bulk` | Bulk delete by ids |
| DELETE | `/api/contacts/all?confirm=true` | Delete every contact in the tenant (drafts and events go with them) |
| POST | `/api/contacts/{contact_id}/eligibility` | Set opt-in eligibility |
| GET | `/api/contacts/tags` | All tags (`{"tags": [...]}`) |
| POST | `/api/contacts/{contact_id}/tags?tag=` | Add tag |
| DELETE | `/api/contacts/{contact_id}/tags/{tag}` | Remove tag |

### Lists and folders

| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/api/lists` | List / create |
| GET / PATCH / PUT / DELETE | `/api/lists/{list_id}` | Read / update / delete |
| GET | `/api/lists/{list_id}/contacts` | Members |
| POST | `/api/lists/{list_id}/contacts/add` | Add members |
| POST | `/api/lists/{list_id}/contacts/remove` | Remove members |
| POST | `/api/lists/{list_id}/contacts/remove-duplicates` | Dedupe against other lists |
| POST | `/api/lists/{list_id}/contacts/remove-from-other-lists` | Move semantics |
| POST | `/api/lists/{list_id}/contacts/{contact_id}/subscribe` | Subscribe |
| POST | `/api/lists/{list_id}/contacts/{contact_id}/unsubscribe` | Unsubscribe |
| POST | `/api/lists/{list_id}/duplicate` | Duplicate a list |
| POST | `/api/lists/{list_id}/import` | Import into a list |
| GET / PUT | `/api/lists/{list_id}/settings` | Per-list sender/header/footer |
| GET | `/api/lists/{list_id}/stats` | Per-list counters |
| GET / POST | `/api/lists/folders` | List / create folders |
| PATCH / PUT / DELETE | `/api/lists/folders/{folder_id}` | Update / delete folder |

### Drafts, templates and sending

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/drafts` | List drafts |
| POST | `/api/drafts/compose` | Create a personalized draft |
| GET | `/api/drafts/{draft_id}` | Read a draft |
| POST | `/api/drafts/{draft_id}/update` | Edit a draft |
| POST | `/api/drafts/{draft_id}/redraft` | Regenerate with the agent |
| POST | `/api/drafts/{draft_id}/send` | Send one draft |
| GET / POST | `/api/templates` | List / create |
| POST | `/api/templates/{template_id}` | Update |
| DELETE | `/api/templates/{template_id}` | Delete |
| POST | `/api/templates/{template_id}/duplicate` | Duplicate |
| GET | `/api/templates/categories` | Category list |
| POST | `/api/templates/expand` | Expand variables without saving |
| POST | `/api/templates/use` | Render a template for a contact |
| GET | `/api/queue/status` | Queue state and pending drafts |
| POST | `/api/queue/run` | One synchronous send pass |
| POST | `/api/queue/run-all` | Compose for selected contacts, drain the queue, and hand any pacing leftover to a background job (`queued`/`job_id`) |
| POST | `/api/queue/run-async` | Queue a background send job (drains the queue) |
| GET | `/api/queue/jobs/{job_id}` | Async job progress |
| POST | `/api/queue/followups` | Generate due follow-up drafts |
| POST | `/api/run` | One full autopilot pass for the caller's tenant (rate limited) |

### Campaigns and experiments

| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/api/campaigns` | List / create |
| GET / PATCH / DELETE | `/api/campaigns/{campaign_id}` | Read / update / delete |
| POST | `/api/campaigns/{campaign_id}/pause` | Pause |
| POST | `/api/campaigns/{campaign_id}/cancel` | Cancel |
| POST | `/api/campaigns/{campaign_id}/duplicate` | Duplicate |
| GET | `/api/campaigns/{campaign_id}/stats` | Results |
| GET | `/api/campaigns/summary` | Aggregate counters |
| GET / POST | `/api/ab-tests` | List / create experiments |
| GET / PATCH / DELETE | `/api/ab-tests/{test_id}` | Read / update / delete |
| GET | `/api/ab-tests/results` | Results across experiments |
| GET | `/api/ab-tests/{test_id}/results` | Per-variant results |
| POST | `/api/ab-tests/{test_id}/variants` | Add variant |
| PATCH / DELETE | `/api/ab-tests/{test_id}/variants/{variant_id}` | Update / remove variant |

### Deliverability

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/smtp/status` | Current SMTP config (password never returned) |
| POST | `/api/smtp/config` | Save SMTP config |
| POST | `/api/smtp/test` | Test connection without sending |
| GET | `/api/inbox` | Stored messages plus IMAP configured flag |
| POST | `/api/inbox/sync` | Read-only IMAP sync |
| GET | `/api/verifications` | List results |
| GET | `/api/verifications/stats` | Counts by status |
| GET / DELETE | `/api/verifications/{verification_id}` | Read / delete |
| POST | `/api/verifications/{verification_id}/reverify` | Re-check |
| POST | `/api/verifications/check` | Check one address |
| POST | `/api/verifications/bulk` | Start a bulk job |
| GET | `/api/verifications/bulk/{job_id}` | Poll job |
| GET | `/api/tracking` | Per-contact engagement attribution |
| GET | `/api/track/open/{token}` | Public 1x1 pixel (no auth) |
| GET | `/api/track/click/{token}?url=` | Public redirect (no auth) |

### Agents, replies and scheduling

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/agents/status` | All agent availability |
| POST | `/api/agents/personalize` | Personalize for a contact |
| POST | `/api/agents/send` | Direct send |
| GET | `/api/agents/test-smtp` | SMTP probe |
| POST | `/api/agents/auto-reply` | Auto-respond to a reply |
| GET | `/api/agents/calendar` | List calendars |
| POST | `/api/agents/calendar/event` | Create event |
| POST | `/api/agents/brain/enhance-subject` | Subject optimization |
| POST | `/api/agents/brain/enhance-body` | Body refinement |
| POST | `/api/agents/brain/alternatives` | A/B variants |
| POST | `/api/agents/brain/summarize` | Thread summary |
| POST | `/api/agents/brain/action-items` | Action item extraction |
| POST | `/api/replies/analyze` | Classify a reply |
| GET | `/api/replies/events/{contact_id}` | Reply events for a contact |
| GET | `/api/scheduling/status` | Scheduled jobs and next runs |
| POST | `/api/scheduling/autopilot` | Toggle autopilot |
| POST | `/api/scheduling/run-now` | Trigger a run |
| GET | `/api/scheduling/history` | Recent runs |

### Settings and team

| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/api/settings` | Read / update tenant settings (includes `tracking_enabled`) |
| GET | `/api/tenants` | Current tenant |
| GET / POST | `/api/tenants/members` | List / invite members |
| PATCH / DELETE | `/api/tenants/members/{member_id}` | Change role / remove |

## Configuration

See `.env.example` for the full list. The values that most affect behaviour:

| Variable | Effect |
|---|---|
| `LOCAL_TENANT_NAME` / `LOCAL_USER_EMAIL` | Identity of the implicit workspace used when a request carries no token |
| `DATABASE_URL` | MySQL/MariaDB connection string |
| `JWT_SECRET_KEY` | Signing key for optional access tokens |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASS` / `SMTP_FROM` | Sending; blocked until set |
| `IMAP_*` | Read-only inbox sync |
| `AUTOPILOT` + `AUTO_APPROVE` | Both must be true for unattended sending |
| `FOLLOWUPS_ENABLED` | Turns automatic follow-up drafting on or off |
| `BLOCK_PLACEHOLDER_RECIPIENTS` | Default `true`. Refuses reserved/disposable addresses and mail-system mailboxes on every send path. Only turn it off to reproduce placeholder data |
| `MAIL_SUPPRESS_SEND` | Default `false`. Dry-run: records sends without opening SMTP. The test suite sets it |
| `TRACKING_ENABLED` (per tenant, via Settings) | Off by default; gates pixels and link rewriting |

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The suite runs against a throwaway schema derived from `DATABASE_URL` and drops it
on completion, so live data is never modified. It also sets `MAIL_SUPPRESS_SEND=true`
and `BLOCK_PLACEHOLDER_RECIPIENTS=false`: tests use `example.com` recipients, and
without suppression the SMTP credentials in `.env` would make the suite send real
mail from the configured account. Frontend checks are `npm run build` and `npm run lint`.

See [FEATURES.md](FEATURES.md) for which test covers which feature.
