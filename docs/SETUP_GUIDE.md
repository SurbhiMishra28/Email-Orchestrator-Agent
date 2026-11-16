# Email Orchestrator Setup Guide

## Prerequisites

Before installing, ensure you have the following installed:

| Software | Minimum Version | Notes |
|----------|-----------------|-------|
| Python | 3.10+ | 3.13 recommended |
| Node.js | 18+ | 20+ recommended |
| MariaDB | 11.8+ | Running on port 3307 |
| Git | 2.30+ | For cloning |

## Quick Start (Windows)

### 1. Clone the Repository
```bash
git clone <repository-url>
cd email-orchestrator
```

### 2. Set Up MariaDB

#### Start MariaDB Service
```powershell
# Check if MariaDB is running
net start | findstr MariaDB

# If not running, start it
net start MariaDB
```

#### Configure for Test Environment
```sql
-- Connect via MySQL client
mysql -u root -p

-- Drop existing database (if incompatible)
DROP DATABASE IF EXISTS email_orchestrator;

-- Create fresh database
CREATE DATABASE email_orchestrator CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Configure root user for both socket and TCP connections
ALTER USER 'root'@'localhost' IDENTIFIED BY '';
ALTER USER 'root'@'127.0.0.1' IDENTIFIED BY '';
FLUSH PRIVILEGES;

-- Grant all privileges
GRANT ALL PRIVILEGES ON *.* TO 'root'@'localhost' WITH GRANT OPTION;
GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;
FLUSH PRIVILEGES;

-- Exit
EXIT
```

### 3. Configure Environment Variables

Copy the example file and update values:
```bash
copy .env.example .env
```

Edit `.env` with your configuration:
```env
# Database Configuration
DATABASE_URL=mysql+pymysql://root:@localhost:3307/email_orchestrator

# SMTP Configuration (Gmail example)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
SMTP_FROM=your-email@gmail.com
SENDER_NAME=Your Name

# IMAP Configuration
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=your-email@gmail.com
IMAP_PASS=your-app-password
IMAP_POLL_MINUTES=10

# NVIDIA AI (Optional)
NVIDIA_API_KEY=your-nvidia-key
NVIDIA_MODEL=nvidia/llama-3.1-nemotron-70b-instruct

# CORS Origins
CORS_ORIGINS=http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:5173,http://localhost:5173
```

#### Getting Gmail App Password
1. Enable 2-Factor Authentication on your Google account
2. Go to Google Account settings → Security → App passwords
3. Generate new app password for "Mail"
4. Use this password as `SMTP_PASS`

### 4. Install Backend Dependencies
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 5. Install Frontend Dependencies
```bash
cd frontend
npm install
cd ..
```

### 6. Build Frontend
```bash
cd frontend
npm run build
cd ..
```

### 7. Run the Application
```bash
# Start backend server
uvicorn app.main:app --host 127.0.0.1 --port 8000

# In a new terminal, run tests
python -m pytest tests/ -v
```

## Development Setup

### Project Structure
```
email-orchestrator/
├── app/                    # Backend Python code
│   ├── routers/           # API route handlers
│   ├── services/          # Business logic services
│   ├── models/            # Pydantic schemas
│   ├── db.py              # Database models
│   ├── agents.py          # AI agents
│   ├── config.py          # Config loading
│   └── main.py            # FastAPI entry point
├── frontend/              # React frontend
│   ├── src/               # Source code
│   ├── dist/              # Build output
│   └── public/            # Static assets
├── tests/                 # Test files
├── docs/                  # Documentation
├── .env                   # Environment variables
├── requirements.txt       # Production deps
└── requirements-dev.txt   # Development deps
```

### Run Tests
```bash
# All tests
python -m pytest tests/ -v

# Specific test file
python -m pytest tests/test_basic.py -v

# With coverage
python -m pytest tests/ --cov=app --cov-report=html
```

### Auto-reload Development
```bash
# Backend with auto-reload
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend with hot-reload
cd frontend
npm run dev
```

## Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `sqlite:///./email_orchestrator.db` | MariaDB connection string |
| `SMTP_HOST` | Yes | - | SMTP server hostname |
| `SMTP_PORT` | Yes | 587 | SMTP port (587 for TLS, 465 for SSL) |
| `SMTP_USER` | Yes | - | SMTP username (email) |
| `SMTP_PASS` | Yes | - | SMTP password or app password |
| `SMTP_FROM` | Yes | - | From email address |
| `SENDER_NAME` | No | - | Display name for sender |
| `IMAP_HOST` | No | - | IMAP server hostname |
| `IMAP_PORT` | No | 993 | IMAP port |
| `IMAP_USER` | No | - | IMAP username |
| `IMAP_PASS` | No | - | IMAP password |
| `IMAP_POLL_MINUTES` | No | 10 | Minutes between inbox syncs |
| `NVIDIA_API_KEY` | No | - | NVIDIA AI API key |
| `NVIDIA_MODEL` | No | llama-3.1-nemotron-70b-instruct | AI model ID |
| `AUTOPILOT` | No | false | Auto-send approved drafts |
| `AUTO_APPROVE` | No | false | Auto-approve all drafts |
| `DAILY_CAP` | No | 50 | Daily send limit |
| `DOMAIN_CAP` | No | 3 | Per-domain daily limit |
| `CORS_ORIGINS` | No | - | Comma-separated allowed origins |

### Sending Limits (Warm-up)

The system enforces a progressive warm-up period:

| Days Since First Send | Daily Cap |
|----------------------|-----------|
| Days 1-3 | 5 emails |
| Days 4-7 | 10 emails |
| Days 8-14 | 30 emails |
| Day 15+ | 50 emails |

The lower of: warm-up cap, `DAILY_CAP`, and domain cap applies.

---

## Troubleshooting

### Database Connection Issues
```bash
# Check MariaDB is running
net start | findstr MariaDB

# Test connection
mysql -u root -p -h 127.0.0.1 -P 3307 -e "SELECT 1;"

# If connection refused, check port
netstat -an | findstr 3307
```

### SMTP Authentication Failed
1. Verify `SMTP_PASS` is an app password (not account password)
2. Ensure 2FA is enabled on email account
3. Check IP isn't blocked

### Port Already in Use
```bash
# Find process using port 8000
netstat -ano | findstr :8000
# Kill if needed
taskkill /PID <pid> /F
```

### Frontend Build Errors
```bash
cd frontend
rm -rf node_modules
npm install
npm run build
```

### Tests Failing
```bash
# Clear cache
python -m pytest --cache-clear tests/

# Re-initialize database
# In Python shell:
import app.db as db; db.init_db()
```

---

## Production Considerations

1. **Database**: Use a managed MariaDB instance
2. **Secrets**: Use secure secret management (not `.env`)
3. **HTTPS**: Deploy behind reverse proxy with TLS
4. **Logging**: Configure proper log aggregation
5. **Monitoring**: Add health check endpoints for load balancers
6. **Rate Limiting**: Adjust limits based on email provider quotas