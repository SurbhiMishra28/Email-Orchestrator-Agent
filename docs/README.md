# Email Orchestrator Documentation

## Overview

Email Orchestrator is a full-stack application for managing email campaigns, contacts, and templates. It features:

- Contact management with CSV import
- Email template management
- Draft creation and management
- SMTP configuration
- Agent-based email orchestration

## Architecture

### Backend (app/)

- `main.py` - FastAPI application entry point
- `db.py` - Database models and session management (SQLAlchemy)
- `agents.py` - Email agent orchestration logic
- `routers/` - API route handlers
- `models/` - Pydantic schemas

### Frontend (frontend/)

- `src/App.jsx` - Main React application
- `src/main.jsx` - React entry point
- `index.html` - HTML template
- `vite.config.js` - Vite build configuration

## API Endpoints

### State
- `GET /api/state` - Get current application state

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

### Template
- `GET /api/templates` - List templates
- `POST /api/templates` - Create template
- `POST /api/templates/use` - Use template
- `POST /api/templates/expand` - Expand template with contact data
- `PATCH /api/templates/{id}` - Update template
- `DELETE /api/templates/{id}` - Delete template
- `POST /api/templates/{id}/duplicate` - Duplicate template

### Replies (Reply Analyzer Agent)
- `POST /api/replies/analyze` - Analyze and classify incoming email replies
- `GET /api/replies/events/{contact_id}` - Get reply events for a specific contact
- `GET /api/replies/events/search?sender_email=` - Search replies by sender email

### SMTP
- `GET /api/smtp/status` - Get SMTP status
- `POST /api/smtp/config` - Save SMTP config
- `POST /api/smtp/test` - Test SMTP connection

### Queue
- `GET /api/queue/status` - Get queue status
- `POST /api/queue/run` - Run one queue pass (paced sends, caps enforced)
- `POST /api/queue/followups` - Create due follow-up drafts now (never sends)

### Inbox (IMAP)
- `GET /api/inbox?limit=50` - Stored messages plus whether IMAP is configured
- `POST /api/inbox/sync` - Fetch newest mail read-only (`BODY.PEEK`) and store new ones

### Verifications
- `GET /api/verifications` - List stored verification results
- `GET /api/verifications/stats` - Counts by status
- `POST /api/verifications/bulk` - Start a background bulk check
- `GET /api/verifications/bulk/{job_id}` - Poll job progress
- `POST /api/verifications/check` - Check a single address
- `POST /api/verifications/{id}/reverify` - Re-check an existing record

## Configuration

See `.env.example` for all required environment variables.