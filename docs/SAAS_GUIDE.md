# Email Orchestrator SaaS Guide

This guide covers how to deploy Email Orchestrator as a multi-tenant SaaS product.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Multi-Tenant Model](#multi-tenant-model)
3. [Authentication System](#authentication-system)
4. [API Keys](#api-keys)
5. [Subscription Plans](#subscription-plans)
6. [Usage Tracking](#usage-tracking)
7. [Deployment Guide](#deployment-guide)
8. [Billing Integration](#billing-integration)
9. [Security Considerations](#security-considerations)

---

## Architecture Overview

The SAAS implementation adds a multi-tenant layer on top of the existing single-tenant architecture:

```
Internet
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                    API Gateway / Nginx                  │
│  - SSL/TLS termination                                  │
│  - Rate limiting                                        │
│  - CORS handling                                        │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Application                  │
│  - Tenant isolation middleware                          │
│  - JWT authentication                                   │
│  - Role-based access control                            │
└───────────────────────┬─────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│   Tenant A  │ │   Tenant B  │ │   Tenant C  │
│  (Org: Acme)│ │  (Org: Beta)│ │ (Org: Gamma)│
│  - Contacts │ │  - Contacts │ │  - Contacts │
│  - Drafts  │ │  - Drafts   │ │  - Drafts   │
│  - SMTP     │ │  - SMTP     │ │  - SMTP     │
└─────────────┘ ┌─────────────┘ └─────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
┌─────────────────┐ ┌─────────────────┐
│   MariaDB       │ │   Redis Cache   │
│   - Shared      │ │   - Sessions    │
│   - Isolated    │ │   - Rate limits │
│   - Schemas     │ │   - Cache       │
└─────────────────┘ └─────────────────┘
```

### Key Design Decisions

1. **Database Isolation**: Single database with tenant_id on all relevant tables
2. **Authentication**: JWT tokens with user context
3. **Authorization**: Role-based access control (RBAC)
4. **API Keys**: For programmatic access
5. **Usage Limits**: Enforced at the tenant level

---

## Multi-Tenant Model

### Database Schema Extensions

New tables have been added to `app/db.py`:

```python
# Tenant (Organization)
class Tenant(Base):
    id: int
    name: str           # Organization name
    subdomain: str      # Optional subdomain
    plan: str           # free, pro, enterprise
    daily_email_limit: int
    api_key_limit: int
    is_active: bool

# User
class User(Base):
    id: int
    tenant_id: int      # Belongs to a tenant
    email: str
    hashed_password: str
    name: str
    role: str           # admin, user, member
    is_active: bool

# API Key for programmatic access
class APIKey(Base):
    id: int
    user_id: int
    name: str
    key: str            # Generated secret key
    permissions: list
    is_active: bool
    expires_at: datetime

# Usage tracking
class UsageLog(Base):
    id: int
    tenant_id: int
    metric: str         # emails_sent, emails_drafted, etc.
    quantity: int
    period: str         # daily, monthly
```

### Tenant Isolation

All queries must filter by `tenant_id`:

```python
# Example: Get contacts for authenticated user's tenant
contacts = db.query(Contact).filter(
    Contact.tenant_id == current_user.tenant_id
).all()
```

---

## Authentication System

### Registration

Users register to create their account and organization:

```
POST /api/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "secure-password-123",
  "name": "John Doe",
  "tenant_name": "Acme Corporation"
}
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### Login

Existing users authenticate:

```
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "secure-password-123"
}
```

Response: Same as registration - JWT token.

### Token Usage

Include the token in the Authorization header:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Current User

Get the authenticated user's information:

```
GET /api/auth/me
Authorization: Bearer <token>
```

Response:
```json
{
  "id": 1,
  "email": "user@example.com",
  "name": "John Doe",
  "role": "admin",
  "tenant": {
    "id": 1,
    "name": "Acme Corporation",
    "plan": "free",
    "daily_email_limit": 50
  }
}
```

---

## API Keys

### Create API Key

Generate an API key for programmatic access:

```
POST /api/auth/api-keys
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Production Integration",
  "permissions": ["read", "write", "send_emails"]
}
```

Response:
```json
{
  "id": 1,
  "name": "Production Integration",
  "key": "abc123xyz...secret-key-shown-only-once",
  "permissions": ["read", "write", "send_emails"],
  "is_active": true,
  "created_at": "2024-01-15T10:00:00Z"
}
```

⚠️ **Important**: The key is only shown once! Store it securely.

### Use API Key

Authenticate with an API key instead of JWT:

```
Authorization: Bearer abc123xyz...secret-key-shown-only-once
```

### List API Keys

```
GET /api/auth/api-keys
Authorization: Bearer <token>
```

### Revoke API Key

```
DELETE /api/auth/api-keys/{api_key_id}
Authorization: Bearer <token>
```

---

## Subscription Plans

### Plan Tiers

| Plan | Monthly Price | Daily Limit | API Keys | Templates | Support |
|------|---------------|-------------|----------|-----------|---------|
| Free | $0 | 50 emails | 5 | 10 | Community |
| Pro | $29 | 500 emails | 25 | 100 | Email |
| Enterprise | Custom | Unlimited | Unlimited | Unlimited | 24/7 Phone |

### Plan Configuration

Default plans are configured in `app/config.py`:

```python
PLAN_LIMITS = {
    "free": {
        "daily_email_limit": 50,
        "api_key_limit": 5,
        "template_limit": 10,
    },
    "pro": {
        "daily_email_limit": 500,
        "api_key_limit": 25,
        "template_limit": 100,
    },
    "enterprise": {
        "daily_email_limit": 10000,  # Effectively unlimited
        "api_key_limit": 100,
        "template_limit": 1000,
    },
}
```

---

## Usage Tracking

### Metrics Tracked

| Metric | Description |
|--------|-------------|
| emails_sent | Emails successfully sent |
| emails_drafted | Emails created as drafts |
| emails_failed | Failed send attempts |
| replies_received | Inbound replies processed |
| contacts_added | New contacts added |

### Check Usage

```
GET /api/usage
Authorization: Bearer <token>
```

Response:
```json
{
  "period": "2024-01-15",
  "daily": {
    "emails_sent": 23,
    "emails_drafted": 5,
    "replies_received": 2
  },
  "monthly": {
    "emails_sent": 456,
    "emails_drafted": 120,
    "replies_received": 34
  },
  "limits": {
    "daily_email_limit": 50,
    "remaining": 27
  }
}
```

### Enforced Limits

Limits are checked before sending:

```python
# Check daily limit before sending
usage_today = get_today_usage(tenant_id)
if usage_today >= tenant.daily_email_limit:
    raise HTTPException(429, "Daily limit exceeded")
```

---

## Deployment Guide

### Native deployment (MariaDB + systemd + nginx)

This project runs on a local MariaDB/MySQL server — no containers are required.

1. Install MariaDB and create the database:

```sql
CREATE DATABASE email_orchestrator CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'app_user'@'localhost' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON email_orchestrator.* TO 'app_user'@'localhost';
FLUSH PRIVILEGES;
```

2. Point `DATABASE_URL` at that server (default port 3306, or 3307 if MariaDB is
   installed side by side with an existing MySQL):

```env
DATABASE_URL=mysql+pymysql://app_user:secure_password@localhost:3306/email_orchestrator
```

3. Install dependencies and build the dashboard:

```bash
pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
```

4. Run the app. `app.main` serves the built `frontend/dist` itself, so a single
   process is enough:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

5. Keep it running with systemd (`/etc/systemd/system/email-orchestrator.service`):

```ini
[Unit]
Description=Email Orchestrator
After=network.target mariadb.service

[Service]
WorkingDirectory=/opt/email-orchestrator
EnvironmentFile=/opt/email-orchestrator/.env
ExecStart=/opt/email-orchestrator/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
User=email-orchestrator

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now email-orchestrator
```

### Environment Variables for SaaS

```env
# Database
DATABASE_URL=mysql+pymysql://app_user:secure_password@localhost:3306/email_orchestrator

# JWT Secret (Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))")
JWT_SECRET_KEY=your-very-long-secret-key-here

# CORS - Production domain
CORS_ORIGINS=https://app.email-orchestrator.com

# Redis for session/cache
REDIS_URL=redis://localhost:6379

# Stripe for billing
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Email limits (can be overridden per tenant)
DAILY_CAP=50
DOMAIN_CAP=10

# Disable single-user mode
AUTOPILOT=true
AUTO_APPROVE=false
```

### SSL/TLS

Use Let's Encrypt with nginx:

```nginx
server {
    listen 80;
    server_name app.email-orchestrator.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name app.email-orchestrator.com;

    ssl_certificate /etc/letsencrypt/live/app.email-orchestrator.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.email-orchestrator.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Billing Integration

### Stripe Integration

Add billing webhooks:

```
POST /api/billing/webhook
Stripe-Signature: t=...

# Handle events
{
  "type": "invoice.paid",
  "data": {
    "object": {
      "customer": "cus_...",
      "amount_paid": 2900,
      "lines": {...}
    }
  }
}
```

### Subscription API (Add to app/routers/billing.py)

```python
@router.post("/subscribe")
async def create_subscription(
    payment_method: str,
    plan: str = Body(...),
    current_user: User = Depends(get_current_user)
):
    """Create a new subscription for the tenant."""
    pass

@router.get("/status")
async def get_subscription_status(
    current_user: User = Depends(get_current_user)
):
    """Get the tenant's subscription status."""
    pass
```

---

## Security Considerations

### API Security

1. **HTTPS Required**: All production traffic must use HTTPS
2. **CORS**: Restrict to your domain(s)
3. **Rate Limiting**: Implement at the gateway level
4. **SQL Injection**: Using SQLAlchemy ORM (protected by default)
5. **XSS**: Frontend built with React (auto-escapes content)

### Authentication Security

1. **Password Policy**: Minimum 8 characters
2. **JWT Expiry**: 7 days (configurable)
3. **Refresh Tokens**: Implement if needed
4. **API Key Rotation**: Encourage regular rotation

### Data Protection

1. **PII Handling**: Email addresses and contact data
2. **GDPR Compliance**: Implement data export/deletion endpoints
3. **Encryption at Rest**: Enable on database server
4. **Encryption in Transit**: TLS for all connections

### Compliance Notes

When deploying as a SaaS:

- **CAN-SPAM Act**: Include unsubscribe mechanism
- **GDPR**: Implement data export/deletion
- **CASL**: Obtain consent before emailing

---

## Frontend Updates for SaaS

To support the SaaS authentication flow, the frontend needs:

1. **Registration Page**
2. **Login Page**
3. **Dashboard showing tenant info**
4. **API Key management UI**
5. **Usage dashboard**
6. **Subscription page**

### API Client Updates

Update the frontend API client to handle authentication:

```javascript
// Example: Using the auth endpoint
const login = async (email, password) => {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  });
  const data = await response.json();
  localStorage.setItem('token', data.access_token);
  return data;
};

// Attach token to requests
const apiFetch = (url, options = {}) => {
  const token = localStorage.getItem('token');
  return fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${token}`
    }
  });
};
```

---

## Next Steps

1. **Add JWT_SECRET_KEY to .env**
   ```env
   JWT_SECRET_KEY=your-generated-secret-key
   ```

2. **Create database migration** for new tenant tables
   ```bash
   python -c "from app.db import init_db; init_db()"
   ```

3. **Update all existing models** to include `tenant_id` foreign key

4. **Add tenant middleware** to filter queries by tenant

5. **Build frontend pages** for registration, login, API keys

6. **Integrate Stripe billing** webhook handler

7. **Deploy to production** with MariaDB + systemd + nginx + Let's Encrypt

---

## API Endpoints for SaaS

| Endpoint | Method | Description | Requires Auth |
|----------|--------|-------------|---------------|
| `/api/auth/register` | POST | Create account | ❌ |
| `/api/auth/login` | POST | Get JWT token | ❌ |
| `/api/auth/me` | GET | Current user info | ✅ |
| `/api/auth/api-keys` | POST | Create API key | ✅ |
| `/api/auth/api-keys` | GET | List API keys | ✅ |
| `/api/auth/api-keys/{id}` | DELETE | Revoke API key | ✅ |
| `/api/usage` | GET | Usage statistics | ✅ |
| `/api/billing/status` | GET | Subscription status | ✅ |
| `/api/billing/subscribe` | POST | Create subscription | ✅ |

### Background sending and experiments

These endpoints round out the autonomous path. They are tenant-scoped and use
the same authentication as every other `/api` route.

| Endpoint | Method | Description | Requires Auth |
|----------|--------|-------------|---------------|
| `/api/run` | POST | One full autopilot pass; sending continues as a background job | ✅ |
| `/api/queue/run-async` | POST | Queue a run-all send and return `job_id` immediately | ✅ |
| `/api/queue/jobs/{job_id}` | GET | Poll a background send job (`status`, `result`, `error`) | ✅ |
| `/api/track/open/{token}` | GET | Tracking pixel hit (signed, unauthenticated by design) | ❌ |
| `/api/track/click/{token}` | GET | Tracked link redirect (signed, unauthenticated by design) | ❌ |
| `/api/tracking` | GET | Per-contact open/click attribution | ✅ |
| `/api/ab-tests` | GET / POST | List or create experiments | ✅ |
| `/api/ab-tests/{test_id}` | GET / PATCH / DELETE | Read, update or delete an experiment | ✅ |
| `/api/ab-tests/{test_id}/results` | GET | Per-variant results | ✅ |
| `/api/ab-tests/{test_id}/variants` | POST | Add a variant | ✅ |
| `/api/ab-tests/results` | GET | Results across experiments | ✅ |

Both tracking routes are public by design (mail clients cannot send an
`Authorization` header) and validate an HMAC signature over
`(tenant_id, draft_id, link)`, so a forged token cannot attribute engagement to
another tenant. Tracking is still opt-in per tenant via
`Settings.tracking_enabled`.

---

## Testing the SaaS Setup

Run tests after setup:

```bash
# Test authentication
python test_auth.py

# Test tenant isolation
python test_tenant_isolation.py

# Run all tests
python -m pytest tests/ -v
```

---

## Support

For issues with the SaaS deployment, check:

1. [Troubleshooting Guide](TROUBLESHOOTING.md)
2. [Security Guidelines](SECURITY.md)
3. [API Reference](API_REFERENCE.md)