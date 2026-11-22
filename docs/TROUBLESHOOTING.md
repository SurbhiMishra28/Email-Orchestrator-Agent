# Email Orchestrator Troubleshooting Guide

## Common Issues and Solutions

### 1. Database Connection Issues

#### Error: "Can't connect to MySQL server"
```
(2002) Connection refused
```

**Solutions**:
1. Check MariaDB is running:
   ```bash
   net start | findstr MariaDB
   ```
2. Check port 3307 is listening:
   ```bash
   netstat -an | findstr :3307
   ```
3. Verify connection string in `.env`:
   ```env
   DATABASE_URL=mysql+pymysql://root:@localhost:3307/email_orchestrator
   ```

#### Error: "Unknown database 'email_orchestrator'"
```
(1049) Unknown database
```

**Solution**:
```sql
CREATE DATABASE email_orchestrator CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

#### Error: "Access denied for user"
```
(1044) Access denied
```

**Solution**:
```sql
-- Grant permissions
GRANT ALL PRIVILEGES ON email_orchestrator.* TO 'root'@'localhost';
GRANT ALL PRIVILEGES ON email_orchestrator.* TO 'root'@'127.0.0.1';
FLUSH PRIVILEGES;
```

---

### 2. SMTP/Email Sending Issues

#### Error: "SMTPAuthenticationError"

**Solutions**:
1. Verify App Password is correct (not regular password)
2. Ensure 2-Factor Authentication is enabled
3. Generate new App Password if needed
4. Check `SMTP_USER` matches account email

#### Error: "Connection timed out"

**Solutions**:
1. Test SMTP connection manually:
   ```bash
   telnet smtp.gmail.com 587
   ```
2. Check firewall allows outbound SMTP (port 587/465)
3. Verify ISP allows SMTP traffic

#### Error: "Message rejected for policy reasons"

**Solutions**:
1. Check daily sending limits
2. Verify recipient domain isn't blocked
3. Ensure emails aren't marked as spam by recipients

---

### 3. Frontend Issues

#### Error: "Failed to load resource" or blank page

**Solutions**:
1. Check `frontend/dist/` exists and has files:
   ```
   frontend/dist/
   ├── index.html
   ├── assets/
   └── ...
   ```
2. Rebuild frontend:
   ```bash
   cd frontend
   npm run build
   ```

#### Error: "Module not found" in browser console

**Solutions**:
1. Clear browser cache
2. Check asset URLs in `index.html` match actual files
3. Verify `vite.config.js` output directory

#### CORS Errors in Browser Console

**Solution**:
Add your frontend URL to `CORS_ORIGINS` in `.env`:
```env
CORS_ORIGINS=http://localhost:5173,https://your-domain.com
```

---

### 4. Test Failures

#### Error: "Connection refused" in tests

**Solutions**:
1. Ensure server is running:
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
2. Check port 8000 is not in use:
   ```bash
   netstat -an | findstr :8000
   ```

#### Error: "No module named 'app'"

**Solution**:
Run tests from project root:
```bash
cd C:\Users\DELL\Downloads\email-orchestrator
python -m pytest tests/ -v
```

#### Error: "Test database connection failed"

**Solution**:
Ensure MariaDB is running and accessible before tests.

---

### 5. Import/Export Issues

#### CSV Import: "Invalid email" errors

**Solution**:
1. Validate CSV format:
   ```
   email,name,company,role,industry,eligible_to_email
   valid@email.com,John Doe,Acme,CTO,Software,true
   ```
2. Check for:
   - Extra whitespace
   - Missing column headers
   - Invalid email formats

#### Large CSV import times out

**Solutions**:
1. Limit import size in router:
   ```python
   MAX_IMPORT_SIZE = 1000  # rows
   ```
2. Process in batches
3. Show progress indicator in UI

---

### 6. Rate Limiting Issues

#### Error: "Rate limit exceeded"

**Solutions**:
1. Wait for rate limit window to reset
2. Check `slowapi` limits in `main.py`
3. Adjust limits if needed for development:
   ```python
   @limiter.limit("100/minute")  # Increase limit
   ```

#### Sends blocked by pacing

**Solution**:
- Pacing is 60 seconds between sends (by design)
- Check queue status: `GET /api/queue/status`
- Wait for next available slot

---

## Debugging Steps

### 1. Check Server Logs
```bash
# View recent logs
tail -f /path/to/logs/app.log

# Or in console, restart server to see startup messages
uvicorn app.main:app --reload
```

### 2. Check Database
```python
# Python interactive check
python
>>> from app.db import SessionLocal, Contact
>>> db = SessionLocal()
>>> db.query(Contact).count()
0
>>> db.close()
```

### 3. Test Health Endpoint
```bash
curl http://127.0.0.1:8000/health
# Should return: {"status":"healthy",...}
```

A response of `{"status":"degraded"}` with HTTP **503** means the process is up but
the database is not reachable — `checks.database.healthy` is `false`. The app keeps
serving in that state so you can fix `DATABASE_URL` without a redeploy; the probe
fails on purpose so a platform health check reports the broken deploy.

### 4. Check Environment Variables
```bash
python -c "from app.config import settings; print(settings.DATABASE_URL)"
```

### 5. Verify MariaDB Connection
```bash
mysql -u root -p -h 127.0.0.1 -P 3307 -e "SHOW DATABASES;"
```

---

## Log Analysis

### Check Logs Location
Logs are stored in the `Log` table and displayed in the UI. Check database:

```sql
SELECT * FROM log ORDER BY timestamp DESC LIMIT 50;
```

### Common Log Patterns

| Log Level | Description |
|-----------|-------------|
| INFO | Normal operations (created, sent, updated) |
| WARNING | Recoverable issues (blocked sends, validation warnings) |
| ERROR | Failed operations (SMTP errors, database errors) |

---

## Performance Issues

### Slow Database Queries

**Diagnosis**:
```sql
SET profiling = 1;
-- Run your query
SELECT * FROM draft WHERE status = 'sent';
SHOW PROFILES;
```

**Optimization**:
1. Add indexes on frequently queried columns
2. Limit result sets
3. Use pagination

### Memory Leaks

**Symptoms**:
- Server memory grows over time
- Responses slow down
- OOM errors

**Solutions**:
1. Verify database sessions are closed
2. Check for circular references in Python objects
3. Use `async/await` properly for async features

---

## Network Issues

### Cannot connect to MariaDB from application

**Diagnostic**:
```bash
# Test from Python
python -c "import pymysql; print(pymysql.connect(host='localhost', port=3307, user='root', password=''))"
```

**If fails**:
1. Check MariaDB bind address in `my.ini`:
   ```ini
   bind-address = 127.0.0.1
   ```
2. Verify firewall rules
3. Test socket connection works

### IMAP/POP3 Connection Issues

**Test**:
```bash
openssl s_client -connect imap.gmail.com:993 -servername imap.gmail.com
```

**Common issues**:
- IMAP not enabled in email settings
- Wrong port (should be 993 for IMAP SSL)
- Account blocking less secure apps

---

## Recovery Procedures

### Database Recovery

If database is corrupt:
```bash
# Drop and recreate (loss of data)
mysql -u root -p -e "DROP DATABASE email_orchestrator;"
mysql -u root -p -e "CREATE DATABASE email_orchestrator;"
```

### Reset SMTP Configuration
```python
python -c "
from app.db import SessionLocal, SMTPConfig
db = SessionLocal()
db.query(SMTPConfig).delete()
db.commit()
db.close()
"
```

### Clear Logs
```sql
DELETE FROM log;
```

---

## Getting Help

If issues persist:

1. **Check Documentation**: `docs/` directory
2. **Review Logs**: Database Log table and server output
3. **Verify Configuration**: `.env` file settings
4. **Test Components**: Run `test_all.py` or test files
5. **Create Minimal Reproduction**: Isolate the issue