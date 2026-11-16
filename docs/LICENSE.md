# Email Orchestrator Licensing

## Overview

Email Orchestrator is released under the **MIT License**.

## MIT License

Copyright (c) 2024 Email Orchestrator Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## Third-Party Licenses

### Backend Dependencies

| Package | License | Notes |
|---------|---------|-------|
| fastapi | MIT | Web framework |
| uvicorn | BSD-3-Clause | ASGI server |
| sqlalchemy | MIT | ORM |
| pydantic | MIT | Data validation |
| jinja2 | BSD-3-Clause | Template engine |
| langchain-* | MIT | AI agents |
| slowapi | MIT | Rate limiting |
| python-dotenv | MIT | Environment loading |
| email-validator | BSD-3-Clause | Email validation |
| apscheduler | Apache-2.0 | Background jobs |
| dnspython | BSD-3-Clause | DNS lookups |
| pymysql | GPL-2.0/MIT | MySQL driver |

### Frontend Dependencies

| Package | License | Notes |
|---------|---------|-------|
| React | MIT | UI library |
| Vite | MIT | Build tool |
| Tailwind CSS | MIT | CSS framework |
| lucide-react | ISC | Icons |

---

## Usage Notes & Important Considerations

### 1. SMTP Credentials
**Never commit email passwords or app passwords to version control.** Always use environment variables (`.env` file) for sensitive credentials.

### 2. Database Credentials
Use environment variables for all database connection strings. The default configuration uses localhost without authentication for development only.

**Production recommendation**:
```env
DATABASE_URL=mysql+pymysql://app_user:strong_password@db-host:3307/email_orchestrator
```

### 3. API Keys
Store AI service API keys (NVIDIA) in secure environments and never in code repositories.

### 4. Legal Compliance
When sending emails through this system, ensure compliance with applicable laws:

#### CAN-SPAM Act (US)
- Include unsubscribe mechanism in all bulk emails
- Use accurate "From" addresses
- Honor opt-out requests promptly
- Include physical mailing address

#### GDPR (EU)
- Obtain explicit consent before emailing EU residents
- Provide data export functionality
- Honor "right to be forgotten" requests
- Implement proper privacy notices

#### CASL (Canada)
- Obtain express or implied consent
- Include sender identification
- Provide unsubscribe mechanism

### 5. Email Sending Best Practices
- Always use authenticated SMTP (App Passwords for Gmail)
- Follow rate limits of your email provider
- Maintain clean contact lists (remove bounces, spam complaints)
- Implement proper feedback loops
- Monitor deliverability metrics

### 6. Development vs Production
This project is configured for development use with:
- SQLite fallback available
- No authentication on API endpoints
- Root database user (not recommended for production)
- Local-only CORS origins

For production deployment, configure:
- Proper authentication system
- Non-root database user
- HTTPS/TLS encryption
- Production-ready CORS settings
- Log aggregation and monitoring