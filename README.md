# MailMatrix - Email Orchestrator

A React dashboard backed by a Python/FastAPI service. LangChain powers the optional
NVIDIA-compatible chat model and agent tools; MySQL/MariaDB is the primary database 
(SQLite fallback available for development without database).

**Agent Name**: MailMAtrix
**Logo**: Purple gradient envelope with "MA" text

The orchestrator coordinates agents for contact personalization, email drafting,
SMTP sending, reply classification, follow-ups, and IMAP inbox sync. Without an
LLM key, built-in email templates are used. Sending is disabled until SMTP is
configured. Calendar booking and long-term agent memory are not implemented; the
Agents page labels them as unavailable rather than pretending they run.

Outbound email is plain text with no HTML or tracking pixel, sent through the
configured authenticated SMTP relay, and paced at least 60 seconds apart. Open
tracking is disabled for new messages. A warm-up cap limits the workspace to 5 emails
per rolling 24 hours on days 1–3, 10 on days 4–7, 30 on days 8–14, and 50 thereafter;
the lower of this cap, `DAILY_CAP`, and the recipient-domain cap always applies.
Warm-up day 1 begins with the first successful send. Contacts are ineligible by
default and must be explicitly marked eligible in Contacts or imported with an
`email_permission` CSV column set to `true` for permission-based recipients.

The in-process scheduler checks for due follow-ups every 6 hours: a day-3 and a
day-5 draft per sent email, stopping after day 8. It never sends automatically;
each draft still requires approval. The same scheduler polls IMAP every
`IMAP_POLL_MINUTES` (default 10) when credentials are set. Setting both
`AUTOPILOT` and `AUTO_APPROVE` makes it run a queue pass every 5 minutes; both
default to off. Run a single backend worker so only one scheduler is active.

## Requirements

- Python 3.10+
- Node.js 18+
- MySQL 8+ or MariaDB 10.6+ (or use SQLite for development)

## Setup

1. Create a MySQL/MariaDB database (optional for SQLite fallback).
2. Copy `.env.example` to `.env` and set your configuration.
   - For MySQL/MariaDB: `DATABASE_URL=mysql+pymysql://user:password@127.0.0.1:3306/email_orchestrator`
   - For SQLite (development): `DATABASE_URL=sqlite:///./email_orchestrator.db`
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

## Configuration

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
- `IMAP_HOST`, `IMAP_PORT`, `IMAP_USER` and `IMAP_PASS` enable inbox sync. Mail is
  fetched read-only (`BODY.PEEK`), so nothing is marked as read in your mailbox.
- `FOLLOWUPS_ENABLED=false` turns off automatic follow-up drafting.
- `CORS_ORIGINS` restricts cross-origin access; the default only allows localhost.

The application has no user accounts or login. It binds to `127.0.0.1` and is
meant to run on your own machine; do not expose port 8000 to the internet.

See `.env.example` and [the setup guide](docs/README.md) for all settings.

## Tests

Tests read the currently configured database (SQLite by default) and do not
modify application data:
   ```powershell
   python -m pip install -r requirements-dev.txt
   python -m pytest -q
   ```

The frontend build check is `npm run build` in `frontend/`.