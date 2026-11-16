# Email Orchestrator Changelog

All notable changes to the Email Orchestrator project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **PersonalizedEmailAgent** - New agent for contact-specific email personalization with AI enhancement
- **SenderAgent** - Low-level SMTP sending agent with validation and error handling
- **CalendarAgent** - Meeting scheduling integration (Google Calendar, Microsoft, Calendly, manual)
- **AIBrainAgent** - AI intelligence layer for content optimization and A/B testing

### Changed
- Updated agent documentation to reflect complete implementation
- Added comprehensive docstrings to all agent classes

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