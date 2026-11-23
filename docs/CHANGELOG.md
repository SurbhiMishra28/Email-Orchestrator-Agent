# Email Orchestrator Changelog

All notable changes to the Email Orchestrator project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Inverted dark theme** - The dashboard was rebuilt on a near-black sage palette (`#060b09` floor, `#7fb39d` accent) with a cinematic splash. The `ink` ramp is inverted (low numbers are the page floor, high numbers are the brightest text) so existing utility classes keep their meaning
- **PersonalizedEmailAgent** - New agent for contact-specific email personalization with AI enhancement
- **SenderAgent** - Low-level SMTP sending agent with validation and error handling
- **CalendarAgent** - Shares the Calendly booking link saved in Settings; event creation is refused because invitees book through that link
- **AIBrainAgent** - AI intelligence layer for content optimization and A/B testing
- **Zero-touch autopilot** - `POST /api/run` drafts intros, syncs the inbox, classifies and answers replies, generates follow-ups and sends, with no approval step
- **Queue drain** - `services/send_worker.drain_queue()` keeps passing the queue so a single Run delivers the whole ready batch instead of one paced email
- **Batch sends drain too** - `/api/queue/run-all` and `/api/queue/run-async` use the same drain, so "Send selected" and campaign sends no longer stop after one email; whatever the bounded synchronous drain cannot finish is returned as `queued: true` with a `job_id`
- **Async send jobs** - `POST /api/queue/run-async` plus `GET /api/queue/jobs/{job_id}` run sends on the background worker so a large batch never holds an HTTP request open
- **Template aliases** - `INTRO_CATEGORIES` / `FOLLOWUP_CATEGORIES` accept the legacy `personalized_mail`, `outreach`, `initial` and `followups_mail` spellings
- **CSV import eligibility** - `CSVImport.default_eligible` keeps imports mailable when the file has no `email_permission` column
- **Bulk contact deletion** - `DELETE /api/contacts/all?confirm=true` and `DELETE /api/contacts/bulk` remove contacts with their drafts, events, list memberships and verification links
- **Engagement tracking** (opt-in) - HMAC-signed open/click pixels via `/api/track/open/{token}` and `/api/track/click/{token}`, attribution at `/api/tracking`
- **A/B testing** - `/api/ab-tests` experiment and variant CRUD with deterministic variant assignment and per-variant results
- **Recipient deliverability guard** - `services/recipients.py` refuses reserved domains (`example.com`, `*.test`, `localhost`), disposable inboxes and mail-system mailboxes (`mailer-daemon@`, `postmaster@`, `no-reply@`) on every send path: contact creation, edit, CSV import, intro drafting, queue selection and send, and direct agent send
- **Bounce handling** - `services/bounces.py` recognises delivery-failure notifications in the synced inbox, blacklists the failed address (`email_blacklisted`), marks the contact ineligible, fails its outstanding drafts and increments `Campaign.bounced`; bounces are never auto-answered
- **`MAIL_SUPPRESS_SEND`** - dry-run mode that records a send without opening an SMTP connection; the test suite enables it so it can never mail the real account in `.env`

### Changed
- **Template deletion is guarded** - `DELETE /api/templates/{id}` now answers **409** with a clear message when a campaign or A/B test still references the template, instead of surfacing a raw database error, and the Templates view shows that message inline
- **Sign-in screen restored** - The app asks `GET /api/auth/me` for the stored session on first load and shows the email/password form (with a toggle into workspace registration) when there is no usable one. The rail's avatar button signs out and returns to that form. `POST /api/auth/register` creates the tenant, its first admin and the starter templates
- **`/health` returns 503 when the database is unreachable** - The payload reports `"status": "degraded"` and `checks.database.healthy: false`, so a platform probe fails the deploy instead of reporting a process that cannot serve requests as up. The app still starts and serves when the database is missing at boot; only the probe fails
- **Dashboard theme** - Replaced the light sky-blue palette with the dark sage theme; `red`/`amber`/`blue` utilities map to `danger`/`warn`/`info` scales and all white surfaces use the inverted `ink` ramp
- Updated agent documentation to reflect complete implementation
- Added comprehensive docstrings to all agent classes
- `/api/run` and `/api/scheduling/run-now` return immediately with a `job_id`; sending continues server-side
- Reply handling no longer gates on human review: every reply is classified and answered in the same pass
- All destructive UI actions now use an in-app confirmation modal instead of `window.confirm`
- Replies from unmonitored mailboxes (`no-reply@`, `postmaster@`, daemons) are recorded but never answered
- Queue passes skip blacklisted contacts instead of retrying them

### Removed
- **The demo workspace** - `POST /api/auth/demo`, `app/services/demo.py`, `DEMO_ALLOW_SENDING`, the `demo` flag on `/api/auth/me`, the demo guards in `app/deps.py` and `tests/test_demo_workspace.py`. No workspace ships with seeded sample data: every contact, list, template, campaign and draft is created by its owner
- The 100 fictional contacts imported from `customers-100.csv`, the empty placeholder list they created, and the 154 delivery-failure inbox rows left by earlier sends to placeholder addresses

---

## [1.0.0] - 2024-01-15

### Added
- Initial release
- FastAPI backend with REST API
- React frontend with Vite build
- MariaDB/MySQL database integration
- SMTP email sending with Gmail support
- IMAP inbox synchronization
- Contact management with CSV import
- Email template management with Jinja2
- Draft management system
- Queue-based email sending with rate limiting
- Reply analysis agent for classifying responses
- Follow-up generation agent (day 3, day 5, day 8 workflow)
- Send limits with warm-up caps (5→10→30→50 emails/day)
- AI personalization support via NVIDIA API
- Email verification service (SMTP, MX, catch-all checks)
- Comprehensive test suite (10 passing tests)

### Features
- Contact CRUD operations
- Draft compose, send, list, and status management
- Template creation, usage, and expansion
- SMTP configuration and connection testing
- Queue status and processing management
- Inbox sync and message storage
- Reply analysis and event tracking
- Bulk email verification jobs

### Architecture
- SQLAlchemy ORM with MariaDB backend
- APScheduler for background tasks
- slowapi for rate limiting
- LangChain agents for AI integration
- Pydantic for request/response validation

---

## API Endpoints

### State Management
- `GET /health` - Health check with database status
- `GET /api/state` - Current application state

### Contacts
- `GET /api/contacts` - List contacts
- `POST /api/contacts` - Create contact
- `GET /api/contacts/{id}` - Get contact
- `PATCH /api/contacts/{id}` - Update contact
- `POST /api/contacts/import` - Import CSV

### Drafts
- `GET /api/drafts` - List drafts
- `POST /api/drafts/compose` - Create draft
- `POST /api/drafts/{id}/send` - Send draft

### Templates
- `GET /api/templates` - List templates
- `POST /api/templates` - Create template
- `POST /api/templates/use` - Use template
- `POST /api/templates/expand` - Expand template
- `PATCH /api/templates/{id}` - Update template
- `DELETE /api/templates/{id}` - Delete template

### Queue
- `GET /api/queue/status` - Queue status
- `POST /api/queue/run` - Run queue
- `POST /api/queue/followups` - Generate follow-ups

### SMTP
- `GET /api/smtp/status` - SMTP status
- `POST /api/smtp/config` - Save config
- `POST /api/smtp/test` - Test connection

### Inbox
- `GET /api/inbox` - List messages
- `POST /api/inbox/sync` - Sync inbox

### Replies
- `POST /api/replies/analyze` - Analyze reply
- `GET /api/replies/events/{contact_id}` - Get reply events

### Verifications
- `GET /api/verifications` - List verifications
- `GET /api/verifications/stats` - Verification stats
- `POST /api/verifications/check` - Check single email
- `POST /api/verifications/bulk` - Bulk verification
- `GET /api/verifications/bulk/{job_id}` - Poll job
- `POST /api/verifications/{id}/reverify` - Re-verify

---

## Configuration

### Environment Variables
See `.env.example` for all supported environment variables including:
- `DATABASE_URL` - MariaDB connection string
- `SMTP_*` - SMTP server configuration
- `IMAP_*` - IMAP server configuration
- `NVIDIA_API_KEY` - Optional NVIDIA AI API key
- `AUTOPILOT` - Auto-send enabled
- `AUTO_APPROVE` - Auto-approve drafts
- `DAILY_CAP` - Daily send limit
- `DOMAIN_CAP` - Per-domain send limit

---

## Database Schema

### Tables
- `contacts` - Contact records
- `drafts` - Email drafts
- `templates` - Email templates
- `settings` - Application settings
- `smtp_config` - SMTP configuration
- `events` - Email events
- `logs` - Application logs
- `tool_uses` - AI tool usage tracking
- `email_verifications` - Email verification results
- `verification_jobs` - Bulk verification jobs
- `inbox_messages` - Stored IMAP messages

---

## Send Limits

### Warm-up Caps
| Days Since First Send | Daily Cap |
|----------------------|-----------|
| Days 1-3 | 5 emails |
| Days 4-7 | 10 emails |
| Days 8-14 | 30 emails |
| Day 15+ | 50 emails |

The lower of: warm-up cap, `DAILY_CAP`, and domain cap applies.

---

## Development

### Testing
```bash
# Run all tests
python -m pytest tests/ -v

# Run specific tests
python -m pytest tests/test_basic.py -v
python -m pytest tests/test_send_limits.py -v
```

### Development Mode
```bash
# Backend with auto-reload
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend with hot-reload
cd frontend
npm run dev
```