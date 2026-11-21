# MailMatrix - Email Orchestrator

A React dashboard backed by a Python/FastAPI service. LangChain powers the optional
NVIDIA-compatible chat model and agent tools; MySQL/MariaDB is the primary database 
(SQLite fallback available for development without database).

**Agent Name**: MailMAtrix
**Logo**: Purple gradient envelope with "MA" text

The orchestrator coordinates agents for contact personalization, email drafting,
SMTP sending, reply classification, follow-ups, and IMAP inbox sync. Without an
LLM key, built-in email templates are used. Sending is disabled until SMTP is
configured. Calendly booking links are supported; invitees create calendar events
by booking through Calendly. Google/Microsoft calendar event creation and
long-term agent memory are not configured.

## Key Features

- **Multi-Tenant SaaS Ready**: Multi-tenant architecture with JWT authentication and role-based access control
- **Agent System**: Personalized Email, Reply Analyzer, Auto-Responder, AI Brain, Sender, and Calendar agents
- **Reply Automation**: Automatic reply generation and sending based on reply classification
- **Rate Limits**: Warm-up cap (5-50 emails/day based on tenure), daily cap, domain cap
- **Scheduling**: Follow-ups are automatically queued for days 3 and 5, and stop after a reply or day 8
- **IMAP Sync**: Read-only inbox polling for reply processing
- **Mail Tracking**: The dashboard shows sent mail, follow-up status, replies, and automatic reply outcomes

## Quick Start (SaaS Mode)

### 1. Environment Setup

```bash
copy .env.example .env
```

Configure these key variables:
```env
# Database
DATABASE_URL=mysql+pymysql://root:@localhost:3307/email_orchestrator

# JWT for SaaS Authentication
JWT_SECRET_KEY=your-generated-secret-key

# SMTP for email sending
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
SMTP_FROM=your-email@gmail.com

# IMAP for reply automation (optional)
IMAP_HOST=imap.gmail.com
IMAP_USER=your-email@gmail.com
IMAP_PASS=your-app-password
```

### 2. Start the Server

```bash
# Backend
uvicorn app.main:app --host 127.0.0.1 --port 8000

# Frontend (in another terminal)
cd frontend && npm run build
```

Open <http://127.0.0.1:8000> to access the dashboard.

---

## Full Documentation

| Guide | Description |
|-------|-------------|
| [Docs Index](docs/README.md) | Overview, UI structure, and the complete endpoint list |
| [Core Flows](docs/FLOWS.md) | End-to-end flows with diagrams: import, send, replies, tracking, A/B |
| [Feature Inventory](docs/FEATURES.md) | Every feature with status and the test that covers it |
| [Setup Guide](docs/SETUP_GUIDE.md) | Detailed installation and configuration |
| [SaaS Guide](docs/SAAS_GUIDE.md) | Multi-tenant SaaS deployment |
| [API Reference](docs/API_REFERENCE.md) | Complete API endpoint documentation |
| [Architecture](docs/ARCHITECTURE.md) | System design and components |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues and solutions |

---

## User Interface

The dashboard is a single React app served by the same FastAPI process. The
interface is branded **MailMatrix**.

- **Opening splash**: a full-screen `MailMatrix` wordmark with a loading bar, then a
  fade into the dashboard (skipped under `prefers-reduced-motion`).
- **Theme**: sky-blue accent (`#0ea5e9`) on a neutral ink palette. Every accent
  derives from the `brand` scale in `frontend/tailwind.config.js`.
- **Desktop**: persistent sidebar with grouped navigation (Workspace, Audience,
  Campaigns, Deliverability, Operations), stat tiles, and data tables.
- **Mobile**: the sidebar becomes an off-canvas drawer opened by the hamburger icon
  in the top bar. It closes on navigation, on Escape, and on tapping the scrim, and
  the page behind it is scroll-locked while open.
- **Deep links**: every view has a URL (`/contacts`, `/agents`, `/campaigns`,
  `/experiments`, ...), so refresh and browser back/forward behave as expected.

---

## Legacy Mode (No Users)

The application also runs in a **single-user mode** without authentication. This is
the default: `SINGLE_USER_MODE=true` in `.env`.

- Binds to `127.0.0.1` only (not exposed to internet)
- No user accounts or login required
- All data is shared (single workspace)
- Good for personal use or development

### Requirements

- Python 3.10+
- Node.js 18+
- MySQL 8+ or MariaDB 10.6+ (or use SQLite for development)

### Setup (Legacy Mode)

1. Create a MySQL/MariaDB database (optional for SQLite fallback).
2. Copy `.env.example` to `.env` and set your configuration.
3. Install and start the backend:

   ```powershell
   python -m pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```

4. In another terminal, build the React app:

   ```powershell
   Set-Location frontend
   npm install
   npm run build
   ```

   For frontend development, use `npm run dev`; Vite proxies `/api` to the backend.

Open <http://127.0.0.1:8000>. The API is documented at `/docs`.

The Overview's Recent Activity panel streams high-level agent and method lifecycle events over WebSocket. Live entries are held in memory only; database-backed activity history is unchanged.

---

## Configuration (Legacy Mode)

- `DATABASE_URL` - MySQL/MariaDB connection string (defaults to SQLite for development)
- `NVIDIA_API_KEY` enables LangChain-backed generation; leave it unset to use
  built-in templates.
- `SMTP_HOST`, `SMTP_FROM`, and (when required by your provider) `SMTP_USER` and
  `SMTP_PASS` enable real SMTP sending. Without SMTP configuration, sending is blocked.
- The Settings page can test SMTP connectivity and authentication without sending
  a message.
- Pending drafts can be sent individually from Drafts after saving and testing the
  SMTP settings.
- Contact imports can include `email_permission=true` for opted-in or otherwise
  eligible recipients. Missing or unrecognized values remain ineligible.
- To start hands-off sending after import, configure SMTP and IMAP, set a Calendly
  booking URL in Settings, and enable both **Auto-send** and **Autopilot**. Only
  contacts with explicit email permission are sent messages; existing warm-up,
  daily, and domain limits continue to apply.
- Mail Tracking, Follow-ups, and Replies in the UI update every 15 seconds and
  retain their message history in the database.
- `IMAP_HOST`, `IMAP_PORT`, `IMAP_USER` and `IMAP_PASS` enable inbox sync. Mail is
  fetched read-only (`BODY.PEEK`), so nothing is marked as read in your mailbox.
- `FOLLOWUPS_ENABLED=false` turns off automatic follow-up drafting.
- `CORS_ORIGINS` restricts cross-origin access; the default only allows localhost.

The application has no user accounts or login. It binds to `127.0.0.1` and is
meant to run on your own machine; do not expose port 8000 to the internet.

See `.env.example` and [the setup guide](docs/README.md) for all settings.

---

## Tests

Tests run against a throwaway copy of the configured database
(`email_orchestrator_test` on MariaDB/MySQL, or `test_email_orchestrator.db` for
SQLite) and drop it when the suite finishes, so application data is never
touched:
   ```powershell
   python -m pip install -r requirements-dev.txt
   python -m pytest -q
   ```

The frontend build check is `npm run build` in `frontend/`.

---

## Architecture

The orchestrator coordinates agents for contact personalization, email drafting,
SMTP sending, reply classification, follow-ups, and IMAP inbox sync. Outbound email
is plain text by default, sent through the configured authenticated SMTP relay, and
paced at least 60 seconds apart.

### Engagement tracking (opt-in)

Open and click tracking is **off by default** and enabled per tenant in Settings
(`tracking_enabled`). While it is off, no HTML part, pixel, or wrapped link is ever
added to outbound mail. When a tenant enables it, each tracked draft is sent as
`multipart/alternative`: the original plain-text body is unchanged and an HTML part
carries a 1×1 open pixel plus links routed through `/api/track/click/{token}`.

Those public endpoints carry no user session — a signed HMAC token derived from the
draft and tenant ids is the credential, so a forged token cannot attribute opens or
clicks to another tenant. Redirects only follow absolute `http(s)` targets. Turning
tracking off stops all future pixels; it does not delete events already recorded.


### Sending Limits (Warm-up)

The system enforces a progressive warm-up period:

| Days Since First Send | Daily Cap |
|----------------------|-----------|
| Days 1-3 | 5 emails |
| Days 4-7 | 10 emails |
| Days 8-14 | 30 emails |
| Day 15+ | 50 emails |

The lower of this cap, `DAILY_CAP`, and the recipient-domain cap always applies.
Warm-up day 1 begins with the first successful send. Contacts are ineligible by
default and must be explicitly marked eligible in Contacts or imported with an
`email_permission` CSV column set to `true` for permission-based recipients.