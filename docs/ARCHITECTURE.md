# Email Orchestrator Architecture

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Front-End (React)                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   App.jsx       │  │  Components     │  │   API Client    │  │
│  │  (Entry Point)  │  │   (React UI)    │  │   (fetch API)   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└───────────────────────────────┬──────────────────────────────────┘
                                │ REST API (FastAPI)
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Back-End (Python)                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   main.py       │  │   Agents        │  │   Services      │  │
│  │ (FastAPI App)   │  │ (LangChain)     │  │ (mailer, inbox, │  │
│  │  w/ Scheduler   │  │                 │  │  limits, etc)   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│          │                      │                      │         │
│          ▼                      ▼                      ▼         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │    Routers      │  │    Models       │  │    Database     │  │
│  │  (API Routes)   │  │  (Pydantic)     │  │  (SQLAlchemy)   │  │
│  │                 │  │                 │  │                 │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    External Services                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   MariaDB       │  │   SMTP/IMAP     │  │   NVIDIA LLM    │  │
│  │   (Port 3307)   │  │   (Gmail)       │  │   (Optional)    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Component Overview

### Backend Layers

1. **API Layer** (`app/routers/*.py`)
   - FastAPI route handlers
   - Request/Response validation via Pydantic schemas
   - Database session management

2. **Service Layer** (`app/services/*.py`)
   - `mailer.py` - SMTP email delivery
   - `inbox.py` - IMAP email synchronization
   - `limits.py` - Send rate limiting and pacing
   - `verification.py` - Email verification service
   - `followups.py` - Automated follow-up draft generation

3. **Agent Layer** (`app/agents.py`)
   - Email orchestration logic
   - Template expansion with AI personalization
   - Queue management
   - Reply analysis

4. **Data Layer** (`app/db.py`)
   - SQLAlchemy ORM models
   - Database session factory
   - UTC datetime handling

5. **Configuration** (`app/config.py`)
   - Environment variable loading
   - Application settings with defaults

### Database Schema

| Table | Description |
|-------|-------------|
| `contact` | Contact records with email, name, company, eligibility |
| `draft` | Email drafts with status (draft, sent, blocked) |
| `template` | Jinja2 email templates with categories |
| `settings` | Global app settings (goals, caps, autopilot) |
| `smtp_config` | SMTP server configuration |
| `inbox_message` | Stored IMAP messages |
| `event` | Email events (sent, replied, bounced) |
| `log` | Application event logs |
| `tool_use` | AI agent tool usage tracking |
| `email_verification` | Email verification results |
| `verification_job` | Bulk email verification jobs |

### Frontend Structure

```
frontend/src/
├── App.jsx          # Main application with routing/state management
├── main.jsx         # React entry point
└── components/      # (if exists) Reusable UI components
```

## Data Flow Patterns

### Email Send Flow
1. User creates draft via `/api/drafts/compose`
2. Draft saved with status "draft"
3. Queue manager processes via `/api/queue/run`
4. `check_send_allowed()` validates limits
5. `send_email()` delivers via SMTP
6. Draft status updated to "sent", event logged

### Inbox Sync Flow
1. Scheduler triggers `sync_inbox()` every `IMAP_POLL_MINUTES`
2. IMAP fetches messages with `BODY.PEEK`
3. Messages parsed and stored in `inbox_message`
4. UI displays via `/api/inbox`

### Template Expansion Flow
1. Template variables collected from contact
2. Jinja2 renders subject/body
3. If NVIDIA_API_KEY set, AI personalization applied
4. Result returned to caller

## Threading Model

- **Main Thread**: FastAPI request handling
- **Scheduler**: APScheduler AsyncIO (runs in same process)
- **Background Tasks**: Used for email sending to prevent blocking

## Security Considerations

- SMTP credentials never returned in API responses
- CORS enabled for localhost development
- Rate limiting via slowapi
- Email validation before processing
- Database credentials not exposed