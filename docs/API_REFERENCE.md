# Email Orchestrator API Reference

## Authentication

Every `/api` route is workspace-scoped. This app has no login screen: a request
without credentials is served as the single implicit workspace
(`LOCAL_TENANT_NAME`/`LOCAL_USER_EMAIL`), and one is provisioned on first use.

A bearer token is optional and only needed by the programmatic API.
`POST /api/auth/register` creates an additional tenant with its own admin and
starter templates, `POST /api/auth/login` issues a token for it and
`POST /api/auth/refresh-token` renews one.

### Current user

**GET** `/api/auth/me`

Returns the account and its tenant:

```json
{
  "id": 41,
  "email": "owner@company.com",
  "name": "Owner Name",
  "role": "admin",
  "tenant": {
    "id": 12,
    "name": "Acme Inc",
    "plan": "free",
    "daily_email_limit": 50
  }
}
```

The dashboard calls this on first load to label the workspace; it never answers
401. `POST /api/auth/register` creates an additional tenant with its first admin
and starter templates; `POST /api/auth/login` issues a token for it.

## Base URL

```
http://127.0.0.1:8000
```

---

## Endpoints

### Health Check

**GET** `/health`

Returns the health status of the application and its dependencies.

**Response**:
```json
{
  "status": "healthy",
  "checks": {
    "database": {
      "healthy": true,
      "error": null
    }
  },
  "timestamp": "2024-01-15T10:30:00.000000+00:00"
}
```

**Status Codes**:
- 200 OK - Application and database are healthy
- 503 Service Unavailable - Database unreachable; the body is the same shape with `"status": "degraded"` and `checks.database.healthy: false`

The app still starts when the database is missing at boot — `/health` is the probe
that fails, so a platform health check reports the broken deploy instead of passing a
process that cannot serve requests.

---

### State Management

**GET** `/api/state`

Returns the current application state including contacts, drafts, and settings.

**Response**:
```json
{
  "contacts": [...],
  "drafts": [...],
  "settings": {...},
  "templates": [...],
  "logs": [...],
  "tools": [...],
  "analytics": {},
  "smtp": {
    "host": "smtp.gmail.com",
    "port": 587,
    "user": "you@gmail.com",
    "sender": "you@gmail.com",
    "configured": true,
    "authenticated": true,
    "source": "database"
  },
  "imap": {
    "host": "imap.gmail.com",
    "port": 993,
    "user": "you@gmail.com",
    "folder": "INBOX",
    "configured": true,
    "source": "database"
  }
}
```

**Status Codes**:
- 200 OK - State returned successfully

---

### Contacts

#### List Contacts

**GET** `/api/contacts`

Query Parameters:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| skip | int | 0 | Number of records to skip |
| limit | int | 100 | Maximum records to return |

**Response**:
```json
[
  {
    "id": 1,
    "email": "user@example.com",
    "name": "John Doe",
    "company": "Acme Corp",
    "role": "CTO",
    "industry": "Software",
    "phone": null,
    "linkedin": null,
    "notes": null,
    "eligible_to_email": true,
    "created_at": "2024-01-15T10:30:00.000000+00:00",
    "updated_at": "2024-01-15T10:30:00.000000+00:00"
  }
]
```

---

#### Create Contact

**POST** `/api/contacts`

**Request Body**:
```json
{
  "email": "user@example.com",
  "name": "John Doe",
  "company": "Acme Corp",
  "role": "CTO",
  "industry": "Software",
  "eligible_to_email": true
}
```

**Status Codes**:
- 200 OK - Contact created
- 400 Bad Request - Email already exists

---

#### Get Contact

**GET** `/api/contacts/{contact_id}`

**Response**: Same as List Contacts (single object)

**Status Codes**:
- 200 OK - Contact found
- 404 Not Found - Contact does not exist

---

#### Update Contact

**PATCH** `/api/contacts/{contact_id}`

**Request Body**:
```json
{
  "name": "John Smith",
  "eligible_to_email": true,
  "notes": "Met at conference"
}
```

**Status Codes**:
- 200 OK - Contact updated
- 404 Not Found - Contact does not exist

---

#### Import CSV Contacts

**POST** `/api/contacts/import`

**Request** (JSON):
```json
{
  "csv": "email,name,company,role\nuser@example.com,John Doe,Acme Corp,CTO\n",
  "default_eligible": true
}
```

**CSV Format**:
```csv
email,name,company,role,email_permission
user@example.com,John Doe,Acme Corp,CTO,true
```

`email_permission` is optional. When the column is absent, imported rows take
`default_eligible` from the request (default `true`), so a plain
`email,name` file still produces mailable contacts. An explicit
`email_permission` value always wins. Existing contacts are refreshed in place,
not duplicated.

**Response**:
```json
{
  "imported": 50,
  "updated": 3,
  "skipped": 0,
  "automatic_outreach_queued": 0,
  "errors": ["bad-email@: Invalid email address"]
}
```

When the tenant has `AUTOPILOT` and `AUTO_APPROVE` enabled, intro drafts for the
newly eligible contacts are queued as a background task.

---

### Drafts

#### List Drafts

**GET** `/api/drafts`

Query Parameters:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| status | string | null | Filter by status (draft, sent, blocked) |
| skip | int | 0 | Number of records to skip |
| limit | int | 100 | Maximum records to return |

**Response**:
```json
[
  {
    "id": 1,
    "contact_id": 1,
    "subject": "Quick question about your workflow",
    "body": "Hi John,\n\nI noticed you're using Acme Corp's platform...",
    "status": "draft",
    "error_message": null,
    "created_at": "2024-01-15T10:30:00.000000+00:00",
    "sent_at": null
  }
]
```

---

#### Compose Draft

**POST** `/api/drafts/compose`

**Request Body**:
```json
{
  "contact_id": 1,
  "subject": "Quick question",
  "body": "Hi there, I wanted to follow up..."
}
```

**Status Codes**:
- 200 OK - Draft created
- 404 Not Found - Contact does not exist

---

#### Send Draft

**POST** `/api/drafts/{id}/send`

Sends the draft immediately, respecting all rate limits.

**Response**:
```json
{
  "success": true,
  "message": "Draft sent successfully"
}
```

**Status Codes**:
- 200 OK - Draft sent
- 400 Bad Request - Draft is blocked or invalid
- 404 Not Found - Draft does not exist

---

### Templates

#### List Templates

**GET** `/api/templates`

Query Parameters:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| active_only | boolean | true | Only return active templates |

**Response**:
```json
{
  "templates": [
    {
      "id": 1,
      "name": "Intro Email",
      "category": "intro",
      "subject_template": "Quick intro from {{business_name}}",
      "body_template": "Hi {{first_name}},\n\nI'm {{sender_name}} from {{business_name}}...",
      "is_active": true
    }
  ]
}
```

---

#### Create Template

**POST** `/api/templates`

**Request Body**:
```json
{
  "name": "Follow-up Email",
  "category": "followup",
  "subject_template": "Following up on our conversation",
  "body_template": "Hi {{first_name}},\n\nJust checking in on my previous email..."
}
```

**Status Codes**:
- 200 OK - Template created

---

#### Use Template

**POST** `/api/templates/use`

Uses a template to create a draft for a contact.

**Request Body**:
```json
{
  "template_id": 1,
  "contact_id": 1,
  "use_ai": true
}
```

**Response**:
```json
{
  "id": 1,
  "contact_id": 1,
  "subject": "Quick intro from Acme Corp",
  "body": "Hi John,\n\nI'm Alex from Acme Corp...",
  "status": "draft"
}
```

---

#### Expand Template

**POST** `/api/templates/expand`

Returns expanded template content without creating a draft.

**Request Body**:
```json
{
  "template_id": 1,
  "contact_id": 1,
  "variables": {
    "company": "Acme Corp",
    "first_name": "John",
    "last_name": "Doe"
  }
}
```

**Response**:
```json
{
  "subject": "Quick intro from Acme Corp",
  "body": "Hi John,\n\n..."
}
```

---

#### Delete Template

**DELETE** `/api/templates/{id}`

**Status Codes**:
- 200 OK - Template deleted
- 404 Not Found - Template does not exist
- 409 Conflict - A campaign or A/B test still references the template; remove or repoint those first

---

### SMTP Configuration

#### Get SMTP Status

**GET** `/api/smtp/status`

**Response**:
```json
{
  "host": "smtp.gmail.com",
  "port": 587,
  "user": "you@gmail.com",
  "sender": "you@gmail.com",
  "configured": true,
  "authentication_configured": true,
  "source": "database"
}
```

`source` is `database` when the tenant has its own saved row and `environment`
when the values were filled in from the deployment's `SMTP_*` variables. That
fallback only applies to the local single-user tenant, so a second workspace
always reports its own row.

---

#### Save SMTP Config

**POST** `/api/smtp/config`

**Request Body**:
```json
{
  "host": "smtp.gmail.com",
  "port": 587,
  "user": "you@gmail.com",
  "password": "your-app-password",
  "sender": "Your Name"
}
```

A blank `password` keeps the stored one, so the other fields can be re-saved
without retyping the app password.

---

#### Test SMTP Connection

**POST** `/api/smtp/test`

Any field left out or blank is filled from the saved row (or, for the local
tenant, the environment), so an empty body re-checks the mailbox in use.

**Response**:
```json
{
  "ok": true,
  "authenticated": true,
  "message": "Connection successful, authentication passed",
  "configured": true,
  "source": "database",
  "host": "smtp.gmail.com",
  "port": 587
}
```

**Status Codes**:
- 200 OK - Connection successful
- 400 Bad Request - Configuration invalid

---

#### SMTP Defaults

**GET** `/api/smtp/defaults`

Reports what the deployment's environment offers, without the password, so the
dashboard can pre-fill a tenant's row.
```json
{
  "available": true,
  "host": "smtp.gmail.com",
  "port": 587,
  "user": "you@gmail.com",
  "sender": "you@gmail.com",
  "authentication_configured": true
}
```

---

### Queue Management

#### Get Queue Status

**GET** `/api/queue/status`

**Response**:
```json
{
  "scheduler": {
    "alive": true,
    "last_poll": "2024-01-15T10:00:00.000000+00:00"
  },
  "pending_drafts": 5,
  "stats": {
    "total_pending": 10,
    "by_status": {
      "draft": 8,
      "blocked": 2
    }
  }
}
```

---

#### Run Queue

**POST** `/api/queue/run`

Process pending drafts immediately.

**Response**:
```json
{
  "processed": 3,
  "sent": 2,
  "blocked": 1,
  "errors": []
}
```

**Status Codes**:
- 200 OK - Queue processed

---

#### Generate Follow-ups

**POST** `/api/queue/followups`

Create due follow-up drafts based on sent emails.

**Response**:
```json
{
  "message": "Follow-up pass completed",
  "created": 5,
  "skipped": 2
}
```

---

### Inbox (IMAP)

#### List Inbox

**GET** `/api/inbox`

Query Parameters:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| limit | int | 50 | Maximum messages to return |

**Response**:
```json
{
  "configured": true,
  "source": "database",
  "messages": [
    {
      "id": 1,
      "sender": "John Doe <john@example.com>",
      "subject": "Re: Meeting Request",
      "snippet": "Thanks for reaching out...",
      "received_at": "2024-01-15T10:30:00.000000+00:00"
    }
  ]
}
```

---

#### Get Inbox Status

**GET** `/api/inbox/status`

Reports the mailbox used for reply polling. The password is never returned.

**Response**:
```json
{
  "host": "imap.gmail.com",
  "port": 993,
  "user": "you@gmail.com",
  "folder": "INBOX",
  "configured": true,
  "source": "database"
}
```

---

#### Save Inbox Config

**POST** `/api/inbox/config`

**Request Body**:
```json
{
  "host": "imap.gmail.com",
  "port": 993,
  "user": "you@gmail.com",
  "password": "your-app-password",
  "folder": "INBOX"
}
```

A blank `password` keeps the stored one.

---

#### Test Inbox Connection

**POST** `/api/inbox/test`

Blank fields are filled from the saved row (or the environment for the local
tenant). Responds with `ok`, `authenticated`, `message`, `configured`, `source`,
`host` and `port`.

---

#### Inbox Defaults

**GET** `/api/inbox/defaults`

```json
{
  "available": true,
  "host": "imap.gmail.com",
  "port": 993,
  "user": "you@gmail.com",
  "folder": "INBOX"
}
```

---

#### Sync Inbox

**POST** `/api/inbox/sync`

Query Parameters:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| limit | int | 25 | Maximum new messages to fetch |

**Response**:
```json
{
  "configured": true,
  "fetched": 10,
  "new": 4
}
```

Fetching uses `BODY.PEEK`, so nothing is marked read in the mailbox. Each
tenant polls only its own mailbox; a tenant without IMAP credentials is skipped
instead of being fed the operator's mail.

---

### Reply Analysis

#### Analyze Reply

**POST** `/api/replies/analyze`

**Request Body**:
```json
{
  "subject": "Re: Following up",
  "body": "Thanks for the email! I'm interested in learning more.",
  "sender_email": "john@example.com",
  "contact_id": 1
}
```

**Response**:
```json
{
  "reply_type": "positive_response",
  "confidence": 0.92,
  "sentiment": "positive",
  "key_points": ["interested", "asks for more info"],
  "suggested_action": "send_detailed_proposal",
  "needs_human_review": false
}
```

#### Get Reply Events

**GET** `/api/replies/events/{contact_id}`

**Response**:
```json
[
  {
    "id": 1,
    "contact_id": 1,
    "event_type": "positive_response",
    "data": {
      "confidence": 0.92,
      "key_points": ["interested"]
    },
    "timestamp": "2024-01-15T10:30:00.000000+00:00"
  }
]
```

---

#### Search Reply Events

**GET** `/api/replies/events/search?sender_email=john@example.com`

---

### Email Verifications

#### List Verifications

**GET** `/api/verifications`

---

#### Get Verification Stats

**GET** `/api/verifications/stats`

**Response**:
```json
{
  "total": 100,
  "deliverable": 85,
  "undeliverable": 5,
  "risky": 7,
  "inconclusive": 3,
  "not_checked": 0
}
```

---

#### Check Single Email

**POST** `/api/verifications/check`

**Request Body**:
```json
{
  "email": "user@example.com"
}
```

**Response**:
```json
{
  "email": "user@example.com",
  "status": "deliverable",
  "smtp_check": "passed",
  "mx_check": "passed",
  "is_catch_all": false,
  "is_disposable": false
}
```

---

#### Bulk Verification

**POST** `/api/verifications/bulk`

**Request Body**:
```json
{
  "contact_ids": [1, 2, 3, 4, 5],
  "check_smtp": true,
  "check_catch_all": true
}
```

**Response**:
```json
{
  "job_id": 1,
  "status": "pending",
  "total": 5,
  "processed": 0
}
```

#### Poll Bulk Job

**GET** `/api/verifications/bulk/{job_id}`

**Response**:
```json
{
  "id": 1,
  "status": "completed",
  "total": 5,
  "processed": 5,
  "deliverable": 4,
  "undeliverable": 0,
  "risky": 1,
  "inconclusive": 0,
  "created_at": "2024-01-15T10:00:00.000000+00:00",
  "completed_at": "2024-01-15T10:05:00.000000+00:00"
}
```

---

#### Re-verify Email

**POST** `/api/verifications/{id}/reverify`

---

### Agents API

The Agents API exposes all subagents via REST endpoints for use in the UI and external integrations.

#### Personalize Email

**POST** `/api/agents/personalize`

Generate personalized email content for a contact using a template.

**Request Body**:
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| contact_id | int | Yes | - | Contact to personalize for |
| template_id | int | Yes | - | Template to use |
| use_ai | boolean | No | true | Enable AI enhancement |
| custom_values | object | No | - | Custom template variables |

**Response**:
```json
{
  "subject": "Hi John, quick intro from Acme Corp",
  "body": "Dear John Doe, I'm reaching out from Acme Corp...",
  "contact_id": 1,
  "template_id": 5,
  "eligible": true
}
```

**Status Codes**:
- 200 OK - Personalization successful
- 400 Bad Request - Contact not eligible
- 404 Not Found - Contact or template not found

---

#### Send Email

**POST** `/api/agents/send`

Send an email directly using the SenderAgent (bypasses draft creation).

**Request Body**:
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| to_email | string | Yes | - | Recipient email address |
| subject | string | Yes | - | Email subject |
| body | string | Yes | - | Email body |
| from_name | string | No | - | Sender display name |
| from_email | string | No | - | Sender email override |

**Response**:
```json
{
  "success": true,
  "message": "Email sent successfully",
  "message_id": "message-id-here",
  "recipient": "user@example.com"
}
```

**Status Codes**:
- 200 OK - Email sent
- 400 Bad Request - Send failed
- 503 Service Unavailable - SMTP not configured

---

#### Test SMTP Connection

**GET** `/api/agents/test-smtp`

Test the SMTP connection without sending an email.

**Response**:
```json
{
  "success": true,
  "ok": true,
  "authenticated": true,
  "message": "Connection successful, authentication passed",
  "configured": true,
  "authentication_configured": true,
  "host": "smtp.gmail.com",
  "port": 587,
  "source": "database"
}
```

---

#### List Calendars

**GET** `/api/agents/calendar`

List available calendars for the configured provider.

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| provider | string | manual | Calendar provider (`calendly` is the only one this app supports) |

**Response** (provider `calendly`, with a booking URL saved in settings):
```json
{
  "calendars": [
    {"id": "calendly-link", "name": "Calendly booking page", "url": "https://calendly.com/you/intro"}
  ],
  "provider": "calendly"
}
```

**Status Codes**:
- 200 OK - Provider configured
- 501 Not Implemented - No provider configured; the app ships a Calendly booking link, not OAuth calendar sync

---

#### Create Calendar Event

**POST** `/api/agents/calendar/event`

Create a calendar event. Events cannot be created by this app: with Calendly,
invitees book through your link.

**Request Body**:
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| summary | string | Yes | - | Event title |
| start_time | string | Yes | - | ISO format start datetime |
| duration_minutes | int | No | 30 | Event duration |
| attendees | array | No | [] | List of attendee emails |
| description | string | No | - | Event description |
| location | string | No | - | Physical or virtual location |
| provider | string | No | manual | Calendar provider |

**Status Codes**:
- 400 Bad Request - `start_time` is not ISO format
- 501 Not Implemented - No provider can create events; share the Calendly booking link instead

---

#### Enhance Subject Line

**POST** `/api/agents/brain/enhance-subject`

Optimize an email subject line using AI.

**Request Body**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| subject | string | Yes | Subject line to enhance |
| context | object | No | Optional context for personalization |

**Response**:
```json
{
  "original": "Quick question",
  "enhanced": "Quick question about your workflow"
}
```

---

#### Enhance Email Body

**POST** `/api/agents/brain/enhance-body`

Improve email body content using AI.

**Request Body**:
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| body | string | Yes | - | Body text to enhance |
| style | string | No | professional | Tone style (professional, friendly, casual) |

**Response**:
```json
{
  "original": "I wanted to follow up...",
  "enhanced": "I wanted to follow up on my previous email..."
}
```

---

#### Generate Alternatives (A/B Testing)

**POST** `/api/agents/brain/alternatives`

Generate subject/body variants for A/B testing.

**Request Body**:
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| subject | string | Yes | - | Original subject |
| body | string | Yes | - | Original body |
| count | int | No | 3 | Number of alternatives |

**Response**:
```json
{
  "original": {"subject": "Quick question", "body": "I wanted to follow up..."},
  "alternatives": [
    {"subject": "Quick question about your workflow", "body": "I noticed you're using..."},
    {"subject": "Following up", "body": "Just checking in..."},
    {"subject": "Question for you", "body": "Do you have a moment?"}
  ]
}
```

---

#### Summarize Thread

**POST** `/api/agents/brain/summarize`

Summarize an email thread.

**Request Body**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| messages | array | Yes | List of message bodies to summarize |

**Response**:
```json
{
  "summary": "The conversation covers X, Y, and Z topics. Key points include...",
  "messages_analyzed": 5
}
```

---

#### Extract Action Items

**POST** `/api/agents/brain/action-items`

Extract actionable items from email text.

**Request Body**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| email_text | string | Yes | Email body to analyze |

**Response**:
```json
{
  "email_preview": "Thanks for reaching out! I'd like to learn more about...",
  "action_items": [
    "Send pricing information",
    "Schedule a demo call",
    "Follow up by Friday"
  ]
}
```

---

#### Get Agents Status

**GET** `/api/agents/status`

Get status of all agents.

**Response**:
```json
{
  "personalized_email": {
    "status": "available",
    "description": "Generates personalized email content per contact"
  },
  "sender": {
    "status": "configured",
    "description": "Handles SMTP email delivery"
  },
  "calendar": {
    "status": "available",
    "provider": "manual",
    "description": "Meeting scheduling integration"
  },
  "ai_brain": {
    "status": "disabled",
    "model": "nvidia/nllama-3-70b",
    "description": "AI-powered content optimization"
  },
  "reply_analyzer": {
    "status": "available",
    "description": "Classifies incoming email replies"
  }
}
```

## Error Responses

### Standard Error Format
```json
{
  "detail": "Error message describing what went wrong"
}
```

### Common Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request - Invalid input |
| 404 | Not Found - Resource does not exist |
| 422 | Unprocessable Entity - Validation error |
| 429 | Too Many Requests - Rate limit exceeded |
| 500 | Internal Server Error |
| 503 | Service Unavailable - Required service not configured |