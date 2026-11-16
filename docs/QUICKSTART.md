# Email Orchestrator Quick Start Guide

## 5-Minute Setup

### Prerequisites
- Python 3.10+ installed
- Node.js 18+ installed
- MariaDB 11.8+ running on port 3307

### Step 1: Clone and Enter Directory
```bash
git clone <repository-url>
cd email-orchestrator
```

### Step 2: Configure Environment
```bash
copy .env.example .env
# Edit .env with your settings
```

### Step 3: Install Dependencies
```bash
python -m venv venv
venv\Scripts\activate  # Windows
# OR: source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Step 4: Set Up MariaDB
```sql
-- Connect to MariaDB
mysql -u root -p -h 127.0.0.1 -P 3307

-- Create database
CREATE DATABASE email_orchestrator CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Configure root user for both connections
ALTER USER 'root'@'localhost' IDENTIFIED BY '';
ALTER USER 'root'@'127.0.0.1' IDENTIFIED BY '';
FLUSH PRIVILEGES;

-- Exit
EXIT
```

### Step 5: Build and Run
```bash
# Terminal 1: Start backend
uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2: Build frontend
cd frontend
npm install
npm run build
cd ..

# Terminal 3: Run tests
python -m pytest tests/ -v
```

## Verify Installation

Check all components are working:
1. **Backend**: http://127.0.0.1:8000/health → `{"status":"healthy"}`
2. **Frontend**: http://127.0.0.1:8000/ → React app loads
3. **Tests**: All 10 tests pass

---

For detailed instructions, see the full documentation:
- [SETUP_GUIDE.md](SETUP_GUIDE.md) - Complete setup guide
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [API_REFERENCE.md](API_REFERENCE.md) - API endpoints
- [AGENTS.md](AGENTS.md) - Agent documentation