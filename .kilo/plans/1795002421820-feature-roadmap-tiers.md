# Email Orchestrator — Feature Inventory & Build Roadmap

## Purpose

Document what already works, what is claimed-but-broken, and an ordered
Basic → Medium → Advanced roadmap for what to build next.

**Guiding decision:** multi-tenancy is the foundation of Basic. The docs claim it
exists; the code does not enforce it. Building anything per-user before fixing
this means rewriting those queries later.

---

## 1. What Already Exists (verified)

### Backend — 66 endpoints across 11 routers, 79 registered routes

| Router | Endpoints | Working feature |
|---|---|---|
| `contacts.py` | 11 | CRUD, CSV import, tags, bulk delete, eligibility toggle |
| `drafts.py` | 6 | List, compose, update, AI redraft, send single |
| `templates.py` | 8 | CRUD, categories, use/expand, duplicate |
| `smtp.py` | 3 | Status, save config, test connection |
| `settings.py` | 2 | Get/update global settings |
| `queue.py` | 4 | Status, follow-ups, run, run-all (batch) |
| `replies.py` | 2 | Reply classification, per-contact events |
| `verifications.py` | 8 | Single/bulk verify, jobs, stats, re-verify |
| `inbox.py` | 2 | List, manual IMAP sync |
| `tracking.py` | 1 | Aggregated mail/follow-up/reply history |
| `agents.py` | 12 | Personalize, send, SMTP test, calendar, 5 AI-brain tools, status, auto-reply |
| `auth.py` | 5 + 1 stub | Register, login, me, API key create/list/revoke |

### Services (`app/services/`)
- `mailer.py` — SMTP with implicit TLS/STARTTLS, never marks sent without delivery
- `inbox.py` — IMAP read-only via `BODY.PEEK`
- `limits.py` — warm-up (5/10/30/50), daily cap, domain cap, 60s pacing
- `followups.py` — auto-draft at day 3 and 5, stop after day 8
- `verification.py` — syntax, MX, SMTP probe, catch-all, disposable detection
- `outreach.py` — auto-intro for newly imported eligible contacts
- `ws_manager.py` + `live_logs.py` — agent lifecycle events over WebSocket

### Frontend — 8 views in `frontend/src/App.jsx`
Overview, Agents, Contacts, Drafts, Templates, Inbox, Verifications, Settings.

### Migrations
`_ensure_columns()` in `app/db.py` performs additive, idempotent `ALTER TABLE`
upgrades — the established pattern for schema change in this repo (no Alembic).

---

## 2. Known Gaps & Broken Items

| Item | Evidence | Impact |
|---|---|---|
| **No tenant isolation** | `Contact`, `Draft`, `Event`, `Template`, `SMTPConfig`, `Settings`, `InboxMessage`, `EmailVerification`, `VerificationJob`, `ReplyProcessed`, `Log`, `ToolUse` have **no** `tenant_id` | Every user sees all data |
| **No auth on resource routes** | `get_current_user` used only inside `routers/auth.py` | Entire API is public |
| **Singleton settings/SMTP** | `db.query(Settings).first()`, `SMTPConfig.first()` | One SMTP account for all tenants |
| **`analytics` hardcoded empty** | `app/main.py` returns `"analytics": {}` | Overview analytics are fake |
| **`UsageLog` unused** | Model exists; no writer, no reader | No metering for billing |
| **`Invoice` unused** | Model exists; no code touches it | No billing |
| **`TenantMember` unused** | Only written at registration | No team invites |
| **`/api/auth/refresh-token`** | Returns 501 | Users re-login after expiry |
| **`CalendarAgent`** | `manual` provider only | No real calendar booking |
| **No auth UI** | Legacy frontend has no login/register view | SaaS mode unusable from UI |
| **`apps/*` monorepo** | Separate, unfinished; `TemplatesPage.tsx` syntax error, mock routes | Out of scope — ignore |

---

## 3. Basic Tier — Make Multi-Tenancy Real

Foundation. Everything else depends on it.

### 3.1 Add `tenant_id` to resource tables
- Add `tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)` to: `Contact`, `Draft`, `Event`, `Template`, `SMTPConfig`, `Settings`, `InboxMessage`, `EmailVerification`, `VerificationJob`, `ReplyProcessed`.
- `Log`/`ToolUse`: add `tenant_id` nullable — system events may legitimately have none.
- Backfill: single existing tenant (id from `SELECT id FROM tenants LIMIT 1`) owns all legacy rows. If no tenant exists, leave NULL.
- Apply via `_ensure_columns()` (additive `ALTER TABLE ... ADD COLUMN tenant_id INTEGER NULL`) plus index creation, following the existing pattern.

### 3.2 Enforce auth on every resource router
- In `app/routers/api.py`, include resource routers with `dependencies=[Depends(get_current_user)]` so no endpoint can be left unprotected by omission.
- Keep `/api/auth/*` public (register/login).
- Replace `auth.py`'s bare `HTTPBearer()` with `auto_error=True` (already default) and confirm 401 JSON shape.

### 3.3 Scope every query by tenant
- Introduce one helper (e.g. `app/deps.py: def current_tenant_id(user) -> int`) and filter by it in reads **and** writes.
- Highest-risk files: `queue.py:99` (`run-all` selects *all* eligible contacts), `tracking.py` (builds dicts over *all* contacts), `main.py:67` (`get_state_from_db` dumps every row), `outreach.py`, `followups.py`.
- `main.py`'s `/api/state` must scope to the caller; otherwise the dashboard still leaks cross-tenant data.

### 3.4 Per-tenant SMTP and Settings
- Change `SMTPConfig`/`Settings` lookups from `.first()` to `filter_by(tenant_id=...)`.
- Registration must provision a default `Settings` row (currently seeded only globally at startup in `main.py` lifespan).
- Update `lifespan` seeding to run per tenant or move it into registration.

### 3.5 Auth UI
- Add Login/Register views to `frontend/src/App.jsx` (matches existing view-switch pattern), store JWT, attach `Authorization` header in the `api()` helper at `App.jsx:11`.
- Redirect to login on 401.

### 3.6 Finish `refresh-token`
- Implement rotating refresh token (current access tokens are 7-day; keep as-is and add refresh).

### Basic — acceptance
- Two users in two tenants cannot read each other's contacts, drafts, templates, or settings.
- Unauthenticated request to `/api/contacts` returns 401.
- `/api/state` returns only the caller's rows.
- Tests: add cross-tenant isolation tests alongside existing `tests/test_basic.py`.

---

## 4. Medium Tier — Operate the Product

Builds on tenant scoping.

### 4.1 Usage metering
- Write `UsageLog(tenant_id, metric, quantity)` on every successful send, draft, and reply receipt.
- Expose `GET /api/usage` (current period totals).
- Read `Tenant.daily_email_limit` (column exists, unused) in `limits.check_send_allowed` — resolve the lower of plan limit and warm-up cap.

### 4.2 Real analytics
- Replace `"analytics": {}` in `get_state_from_db` with computed totals: sent, replied, reply rate, follow-ups due, per-day series.
- Back it with `Event` aggregation (tenant-scoped).

### 4.3 Teams & invites
- Use the existing `TenantMember` table: `POST /api/tenants/members` (invite), `DELETE` (remove), `PATCH` (role).
- Enforce `User.role` (`admin`/`user`/`member`) — the `require_role` decorator in `app/auth.py` exists but is unused and currently calls `get_current_user()` without credentials, so it needs fixing before use.

### 4.4 Per-tenant rate limiting
- `slowapi` is installed and `main.py` has a global `Limiter`. Add tenant-keyed limits (`key_func` returning tenant id) rather than IP-only.

### 4.5 Contact lists / segments
- Not present in the live app (`apps/api` has mock versions — do not copy). Add `List` + `ListMember` tables and filter send/batch endpoints by list.

### 4.6 Scheduling UI
- APScheduler jobs exist (inbox poll, autopilot). Expose next-run/history and a per-tenant on/off toggle instead of global `AUTOPILOT`.

---

## 5. Advanced Tier — Monetize & Integrate

### 5.1 Billing
- Use the existing `Invoice` model. Integrate Stripe (checkout + webhook → `Invoice` + `Tenant.plan`).
- Gate plan features on `Tenant.plan` / `daily_email_limit` / `api_key_limit`.
- Webhooks need signature verification and must bypass user-JWT auth.

### 5.2 Calendar integration
- Replace the `CalendarAgent` stub with Google Calendar and Microsoft Graph OAuth.
- Store provider tokens per tenant; booking links already supported via `calendly_url`.

### 5.3 Deliverability & engagement tracking
- `Event` already names `email_opened` / `link_clicked` but nothing emits them and the README says outbound is plain text with no tracking pixels.
- Add opt-in open pixel + link wrapping, tenant-scoped, with a documented privacy toggle. This contradicts the current README — decide explicitly before building.

### 5.4 A/B testing
- `AIBrainAgent.generate_alternatives` produces variants but nothing persists them.
- Add variant storage, deterministic assignment per contact, and per-variant result reporting.

### 5.5 Async sending at scale
- Sending is synchronous inside request/queue. Move to a worker queue if tenant volume grows; keep `limits.py` as the single gate.

---

## 6. Risks

| Risk | Mitigation |
|---|---|
| Backfilling `tenant_id` on existing rows is lossy if data belongs to multiple users | Confirm this is a single-user deployment before backfill; otherwise require manual mapping |
| `_ensure_columns` raw SQL is not dialect-neutral (`BOOLEAN DEFAULT 0` breaks on Postgres) | Keep existing MySQL/SQLite handling; add branch if Postgres is targeted |
| Adding auth to routers breaks any existing unauthenticated clients | Ship auth UI in the same change; document the breaking change |
| `run-all` and `/api/state` leak data if missed | Treat 3.3 as a checklist; add explicit cross-tenant tests |
| `require_role` decorator is broken (calls `get_current_user()` with no args) | Fix before relying on RBAC |

---

## 7. Validation Plan

1. `python -m pytest -q` — existing 23 tests must stay green.
2. Add cross-tenant tests: two tenants, assert 404/empty on each other's resources for contacts, drafts, templates, settings, `/api/state`, `run-all`.
3. Auth tests: unauthenticated → 401 on every resource router (iterate over `app.routes`).
4. Frontend: `npm run build` in `frontend/` succeeds.
5. Manual: register → login → create contact → verify isolation with a second account.

---

## 8. Recommended First Slice

Tasks 3.1 → 3.2 → 3.3 only. That converts the security model from "all data
public and shared" to "authenticated and tenant-scoped", which is the single
highest-value change. Ship it with the isolation tests before starting Medium.

---

## 9. Status — Basic tier shipped

Verified by `python -m pytest -q` (30 passed) and `npm run build` (1489 modules).

| Task | Status | Where |
|---|---|---|
| 3.1 `tenant_id` on resource tables | **Done** | `app/db.py` — column on 12 models; `_ensure_tenant_columns()` adds it via `ALTER TABLE ... ADD COLUMN tenant_id INTEGER NULL`, indexes `ix_{table}_tenant_id`, then backfills legacy rows to the first tenant. `users` is included so a pre-multi-tenancy database gets the column too. |
| 3.2 Auth on every resource router | **Done** | `app/routers/api.py` — one `protected = [Depends(get_current_user)]` applied at include time; `/api/auth/*` stays public. |
| 3.3 Tenant-scoped queries | **Done** | `app/deps.py` (`current_tenant_id`, `require_tenant`, `scoped`); all 11 resource routers take `tenant_id: int = Depends(current_tenant_id)` and 404 on cross-tenant ids. `get_state_from_db(tenant_id)`, `tracking.py`, `queue.run-all`, `services/{inbox,limits,followups,outreach}.py` all scoped. |
| 3.4 Per-tenant SMTP + Settings | **Done** | `app/services/provisioning.py: provision_tenant_defaults()` creates settings, SMTP (env-seeded) and starter templates; called at registration and for every tenant at startup. |
| 3.5 Auth UI + JWT header | **Done** | `frontend/src/App.jsx` — `AuthScreen` (login/register), token in `localStorage`, `Authorization: Bearer` in `api()`, session check on load, sign-out, 401/403 → sign-out. |
| 3.6 `refresh-token` | **Done** | `app/routers/auth.py` — reissues a 7-day token for the authenticated user. |
| Analytics | **Done** (was a listed gap) | `app/main.py: _build_analytics(db, tenant_id)` — sent/failed/pending/replied/auto-replies/follow-ups-due plus a 14-day series. |
| `require_role` | **Fixed** | `app/auth.py` — now a real FastAPI dependency factory instead of a broken decorator. |

Tests added: `tests/test_tenant_isolation.py` (7 tests) — cross-tenant
read/list/get/patch/delete 404s, per-tenant settings and SMTP, `/api/state`
scoping, `run-all` isolation, anonymous access behavior, refresh token.
`tests/conftest.py` runs the suite against a throwaway `email_orchestrator_test`
database and provides an authenticated client.

### Deliberate deviations from the plan above

- `Contact.email` stays globally unique. Dropping an inline SQLite `UNIQUE`
  requires a table rebuild, which was rejected as destructive. A duplicate
  email in a second tenant surfaces as `IntegrityError` → HTTP 409 with a
  generic message. Same for `InboxMessage.uid` and `ReplyProcessed.message_uid`.
- `SINGLE_USER_MODE` (default `true`) keeps the local tool working with no
  sign-in: one implicit tenant is provisioned and requests are attributed to
  it. Set `SINGLE_USER_MODE=false` for the multi-tenant deployment.
- `/refresh-token` reissues the access token rather than adding a separate
  rotating refresh-token pair; access tokens were already 7-day.

### Still open

- Advanced 5.3–5.5 shipped — see §11.
- Billing (plans/invoices/Stripe, 5.1) and external calendar integration (5.2)
  remain explicitly excluded from this round of work.

---

## 10. Medium Tier — Shipped

| Task | Status | Where |
|---|---|---|
| 4.1 Usage metering | **Done** | `app/services/usage.py` (`record_usage`, `period_totals`), wired in `app/routers/drafts.py` (send/compose), `app/routers/queue.py` (`run-all` drafts) and `app/main.py:_process_incoming_replies` (replies). `GET /api/usage` returns today/month totals plus the plan allowance; `/api/state` now carries the same block so the dashboard counter is fed. |
| 4.1 Plan enforcement | **Done** | `app/services/limits.py: plan_daily_limit()` + `check_send_allowed` — effective cap is `min(configured_daily_cap, tenant.daily_email_limit, warmup_cap)`; the block message distinguishes "Plan limit reached" from "Daily sending cap". A limit of `0`/`NULL` means unlimited. |
| 4.2 Real analytics | **Done** (delivered with Basic) | `app/main.py:_build_analytics` — sent/failed/pending/replied/auto_replies/followups_due/reply_rate plus a 14-day tenant-scoped `series`. |
| 4.3 Teams & invites | **Done** | `app/routers/tenants.py` — `GET /api/tenants`, `GET/POST/PATCH/DELETE /api/tenants/members`, admin-only via `Depends(require_role("admin"))`. Invites create the account with a one-time generated password (returned once); the last admin cannot be demoted or removed; members cannot remove themselves. |
| 4.4 Per-tenant rate limiting | **Done** | `app/main.py:_rate_limit_key` — the limiter keys on the tenant claim in the bearer token (falling back to user, then IP). Access tokens now carry `tenant_id`. |
| 4.5 Contact lists | **Done** | `app/db.py` `ContactList`/`ContactListMember`; `app/routers/lists.py` CRUD + membership; `GET /api/contacts?list_id=`, and `POST /api/queue/run-all` accepts `list_id`. Removing a contact from a list never mutates the contact. |
| 4.6 Scheduling control | **Done** | `app/routers/scheduling.py` — `GET /api/scheduling/status` (jobs, next run, interval, autopilot flags), `POST /api/scheduling/autopilot` (per-tenant toggle), `GET /api/scheduling/history`, `POST /api/scheduling/run-now`. Shared code path with the timer via `app/main.py:_autopilot_pass`. |
| Frontend | **Done** | `frontend/src/App.jsx` — real list tabs (create/delete/select, add selection to a list), `Automation` view (toggle, next run, run-now, history) and admin-only `Team` view (invite with temporary password, role change, removal). |

Tests added: `tests/test_usage.py` (4), `tests/test_lists.py` (7),
`tests/test_teams.py` (10), `tests/test_scheduling.py` (7). Full suite:
**58 passed**; `npm run build` → 1489 modules, 224 kB JS.

### Notes and deviations

- No billing and no external calendar integration, per the product decision for
  this round. `Invoice` stays an unused model and `Settings.calendly_url` remains
  a plain link.
- Invites do not send email; the generated temporary password is returned once in
  the invite response for an admin to pass on.
- List membership is explicit rows, not a tag convention, so the 4.5 "filter
  send/batch endpoints by list" requirement is met without overloading tags.
- `UsageLog` remains the metering source of truth; `drafts`/`events` stay the
  source for analytics, so the two never disagree by more than a backfill gap.

---

## 11. Advanced Tier (5.3–5.5) — Shipped

| Task | Status | Where |
|---|---|---|
| 5.3 Deliverability & engagement tracking | **Done** | `app/services/tracking.py` — HMAC-signed draft/tenant tokens (`make_token`/`parse_token`), `body_to_html`, anchor wrapping, `PIXEL_GIF`, `record_open`/`record_click` writing `Event(event_type="email_opened"/"link_clicked")`, and `send_html_for_draft` gating every call on `Settings.tracking_enabled`. `app/routers/track.py` serves the public `GET /api/track/open/{token}` (1×1 GIF, `no-store`) and `GET /api/track/click/{token}?url=` (302, http(s) only), mounted in `app/routers/api.py` outside `protected`. `app/services/mailer.py:send_email` gained an optional `html_body` that produces `multipart/alternative` while the plain-text part is preserved. Hooked into `app/routers/drafts.py:send_draft` and both `app/agents.py` send paths. `app/routers/tracking.py` now reports per-contact `opened`/`clicked` plus `opened_drafts`/`clicked_drafts`. |
| 5.3 Privacy toggle | **Done** | `Settings.tracking_enabled` (default `False`) with an additive `_ensure_columns()` migration; exposed on `SettingsBase/Update/Out` and in the Settings UI. `PUBLIC_BASE_URL` in `app/config.py` builds the absolute pixel/click URLs. Auto-replies are never tracked. |
| 5.4 A/B testing | **Done** | `app/db.py` `ABTest`/`ABVariant` (tenant-scoped, weighted, `uq_ab_variant_label`). `app/services/abtesting.py` — deterministic `hash(test_id, contact_id) % total_weight` assignment (`pick_variant`), `active_test_for_template`, `apply_variant` recording `ab_test_id`/`ab_variant_id`/`ab_variant_label` in `Draft.variables`, and `test_results` (sent/opened/clicked/replied/per-variant rates). `app/routers/ab_tests.py` — `/api/ab-tests` CRUD, `/results`, `/variants` add/update/delete, duplicate label → 409, last-variant delete → 409, all-zero weights → 422, foreign template → 404. `queue.py:_create_drafts` applies the variant so `run-all` and `run-async` share one path. |
| 5.5 Async sending | **Done** | `app/services/send_worker.py` — `SendWorker` with an `asyncio.Semaphore` bounded by `SEND_CONCURRENCY`, tracked `SendJob` (`pending`/`running`/`complete`/`failed`), capped job history, and a pluggable runner. `POST /api/queue/run-async` (202 + job id; validates the template first so mistakes are a 4xx) and `GET /api/queue/jobs/{job_id}` (404 for another tenant's job). `/api/queue/run-all` stays synchronous, and every send still goes through `services/limits.py:check_send_allowed`. |
| Frontend | **Done** | `frontend/src/App.jsx` — Experiments view (create a two-variant test against a template, pause/resume, delete, per-variant results table) and an Engagement tracking card in Settings. Settings form now round-trips `tracking_enabled`. |

Tests added: `tests/test_engagement_tracking.py` (10), `tests/test_ab_testing.py` (12),
`tests/test_async_sending.py` (6). Full suite: **108 passed**; `npm run build` →
1489 modules, 270.55 kB JS (73.70 kB gzipped). Route table: **136 routes**
(97 before this tier).

### Notes and deviations

- Tracking is opt-in per tenant and defaults off, which resolves the earlier
  conflict with the README's "plain text, no tracking pixels" claim: that remains
  true unless a tenant turns tracking on. The README's Architecture section now
  documents the toggle and the multipart behaviour.
- The token is derived from `draft_id` + `tenant_id` only, so no schema change was
  needed for 5.3. Events carry `data.draft_id`, which is what per-draft and
  per-variant reporting reads.
- A/B assignment is a pure function of the ids: the same contact always gets the
  same variant, and drafts record the ids so results survive later variant edits or
  test deletion.
- `run-async` deliberately reuses the existing queue pass rather than opening a
  second send path; the worker only changes *when* work runs, never the send gate.
- 5.1 (billing) and 5.2 (external calendar) remain excluded by product decision.

