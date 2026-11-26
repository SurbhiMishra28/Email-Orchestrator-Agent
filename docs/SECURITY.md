# Email Orchestrator Security Guide

## Security Overview

This document outlines the security considerations, best practices, and implementation details for the Email Orchestrator application.

## Security Layers

### 1. Data Protection

#### Sensitive Data Handling
- **SMTP Passwords**: Never returned in API responses
- **Database URLs**: Loaded from environment variables
- **API Keys**: Never logged or stored in code

#### Data at Rest
- MariaDB uses default encryption at rest (configurable)
- Contact data stored with minimum required fields
- Deleted records should use proper `DELETE` statements (not hard deletes)

#### Data in Transit
- SMTP connections use STARTTLS (port 587) or SSL (port 465)
- IMAP connections use SSL/TLS
- Database connections use TCP/IP encryption (MariaDB default)

### 2. Authentication & Authorization

#### Current State
- **No login.** A request without credentials is served as the single implicit
  workspace (`LOCAL_TENANT_NAME` / `LOCAL_USER_EMAIL`), provisioned on first use.
  The public dashboard needs no authentication. Anyone who can reach the process
  reads and writes that workspace and can send as the configured mailbox, so access
  control has to live in front of the app (VPN, identity-aware proxy, HTTP basic
  auth at the platform edge) whenever it is not bound to `127.0.0.1`.
- **Optional bearer tokens** - `POST /api/auth/register` and `/api/auth/login` issue
  7-day tokens for additional tenants, and API keys authenticate scripts. Presenting
  one selects that tenant; every `/api` route still resolves the caller through
  `app.auth.get_current_user` and scopes queries to a single tenant.
- **Role-based access control** - `Depends(require_role("admin"))` gates team management; the last admin of a tenant cannot be demoted or removed

Registration is open: anyone who can reach the instance can create an extra tenant,
which is why such a tenant never inherits the deployment's `SMTP_*` credentials.
Gate `POST /api/auth/register` at the proxy if the instance is private.

### 3. Rate Limiting

#### Implemented Limits
- **slowapi** middleware (per-IP rate limiting)
- **Send limits** per contact (60-second pacing)
- **Daily caps** (`DAILY_CAP` ceiling, default 10; no warm-up ramp)

#### Configuration
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/send")
@limiter.limit("10/minute")
def send_email(request: Request, ...):
    ...
```

### 4. Input Validation

#### Email Validation
```python
from email_validator import validate_email, EmailNotValidError

try:
    validated = validate_email(email)
    normalized = validated.email
except EmailNotValidError as e:
    raise HTTPException(status_code=400, detail=str(e))
```

#### CSV Import Safety
- Row-by-row validation before batch insert
- Individual error reporting for failed rows
- Maximum file size limits enforced

### 5. Error Handling

#### Secure Error Messages
- Generic errors returned to client
- Detailed errors logged server-side
- No stack traces exposed in production

```python
try:
    send_email(...)
except SMTPAuthenticationError:
    logger.error(f"SMTP auth failed for {recipient}")
    raise HTTPException(status_code=500, detail="Delivery failed")
```

### 6. CORS Configuration

#### Development Settings
```env
CORS_ORIGINS=http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:5173,http://localhost:5173
```

#### Production Recommendation
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 7. Database Security

#### Connection String
```
mysql+pymysql://root:@localhost:3307/email_orchestrator
```

**Production hardening**:
```
mysql+pymysql://app_user:strong_password@db-host:3307/email_orchestrator?charset=utf8mb4
```

#### Best Practices
- Use dedicated application user (not root)
- Enable SSL for remote connections
- Regular backup procedures
- Database user with minimal privileges

### 8. SMTP Security

#### Gmail/Provider Requirements
- Use App Passwords (not account passwords)
- Enable 2FA on email accounts
- Monitor sending quotas
- Use dedicated sending domains

#### Configuration
```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587  # STARTTLS (recommended)
# OR
SMTP_PORT=465  # SSL
```

### 9. AI Safety

#### NVIDIA API Key Protection
```python
# Never log API keys
logger.debug(f"Using model: {model}")  # Safe

# Validate key format
if not api_key.startswith('nvapi-'):
    raise ValueError("Invalid NVIDIA API key format")
```

#### Response Validation
- Validate AI-generated content before sending
- Strip potentially dangerous content
- Log all AI interactions for audit

## Security Checklist

### Before Production Deployment

- [ ] Put access control in front of the app (it ships with no login)
- [ ] Change default database user from root
- [ ] Enable HTTPS with valid TLS certificate
- [ ] Configure proper CORS origins
- [ ] Set up rate limiting limits based on provider quotas
- [ ] Rotate all default passwords/API keys
- [ ] Enable audit logging
- [ ] Configure backup procedures
- [ ] Set up monitoring and alerting
- [ ] Review data retention policies
- [ ] Implement CSRF protection
- [ ] Add security headers (CSP, X-Frame-Options, etc.)

### Environment Variables Security

Never commit `.env` files to version control. Create `.env.example`:
```bash
# Copy to .env and fill in real values
DATABASE_URL=
SMTP_HOST=
SMTP_USER=
SMTP_PASS=
```

### Database Credentials Rotation

```sql
-- Rotate password periodically
ALTER USER 'app_user'@'localhost' IDENTIFIED BY 'new-strong-password';
FLUSH PRIVILEGES;
```

## Compliance Considerations

### GDPR (if applicable)
- Provide data export functionality
- Implement right to be forgotten (contact deletion)
- Log consent for email contacts
- Encrypt personal data at rest

### CAN-SPAM Act
- Include unsubscribe mechanism in all bulk emails
- Use accurate "From" addresses
- Honor opt-out requests promptly
- Include physical mailing address

### Email Deliverability
- Authenticate with SPF, DKIM, DMARC
- Use consistent sending IPs
- Monitor spam complaints
- Maintain clean contact lists

## Security Monitoring

### Log Important Events
```python
# Authentication attempts
logger.info(f"Login attempt for {username} from {ip_address}")

# Failed deliveries
logger.warning(f"Email blocked: {reason}")

# Rate limit violations
logger.warning(f"Rate limit exceeded: {ip_address}")
```

### Audit Trail
- All contact imports/exports
- Draft creation and sending
- Configuration changes
- User authentication events

## Incident Response

If security breach is suspected:

1. **Immediately**:
   - Disable affected accounts
   - Rotate exposed credentials
   - Block suspicious IPs

2. **Investigate**:
   - Check logs for unauthorized access
   - Identify data in scope
   - Document timeline

3. **Report**:
   - Notify affected users if contact data exposed
   - Follow regulatory reporting requirements

4. **Remediate**:
   - Apply security patches
   - Update security documentation
   - Conduct security review