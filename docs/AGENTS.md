# Email Orchestrator Agents

## Overview

The Email Orchestrator uses LangChain-compatible agents for intelligent email operations. Each agent follows a defined pattern for context management, tool usage, and response generation.

## Agent Types

### 1. Email Orchestrator Agent (Base Functions)

**File**: `app/agents.py`

The core functions responsible for:
- Contact personalization
- Subject line generation
- Email body crafting
- Template expansion with variable substitution
- AI-powered email enhancement (when NVIDIA API key is configured)

**Key Functions**:
```python
def expand_template_variables(template_str: str, variables: Dict[str, Any]) -> str
def get_llm_client() -> Optional[ChatNVIDIA]
def expand_template_with_ai(draft: Draft, template_str: str, use_ai: bool = True) -> str
```

**Variables Available**:
- `company` - Contact's company name
- `first_name` - Contact's first name
- `last_name` - Contact's last name
- `role` - Contact's role/title
- `industry` - Contact's industry
- `goal` - Current campaign goal
- `business_name` - Your company name
- `business_offer` - Your company's offer
- `timestamp` - Current UTC timestamp

---

### 2. Personalized Email Agent

**File**: `app/agents.py` - `PersonalizedEmailAgent` class

**Purpose**: Generate personalized email content for each contact

**Process**:
1. Load contact information
2. Retrieve relevant template
3. Expand Jinja2 variables with contact data
4. If AI enabled: enhance with NVIDIA model personalization
5. Return formatted email with subject and body

**Example Usage**:
```python
from app.agents import PersonalizedEmailAgent

agent = PersonalizedEmailAgent(
    contact_id=1,
    template_id=5
)
result = agent.personalize(use_ai=True)
# Returns: {"subject": "Hi John, ...", "body": "Dear John Doe, ..."}
```

**Methods**:
```python
def personalize(
    self,
    subject_template: str = None,
    body_template: str = None,
    use_ai: bool = True
) -> Dict[str, str]
```

---

### 3. Reply Analyzer Agent

**File**: `app/agents.py` - `ReplyAnalyzerAgent` class

**Purpose**: Analyze incoming email replies to classify sentiment and determine next action

**Analysis Outputs**:
- `reply_type`: Classification (positive_response, negative_response, question, spam, no_reply_needed)
- `confidence`: Float score 0.0-1.0
- `sentiment`: positive, neutral, negative
- `key_points`: Extracted important information
- `suggested_action`: next_steps, follow_up, archive, etc.

**Endpoint**: `POST /api/replies/analyze`

**Request Body**:
```json
{
  "subject": "string",
  "body": "string",
  "sender_email": "string",
  "contact_id": 1
}
```

**Response**:
```json
{
  "reply_type": "positive_response",
  "confidence": 0.95,
  "sentiment": "positive",
  "key_points": ["interested in pricing", "asks about trial"],
  "suggested_action": "send_proposal",
  "needs_human_review": false
}
```

**Example Usage**:
```python
from app.agents import ReplyAnalyzerAgent

agent = ReplyAnalyzerAgent(contact_id=1)
result = agent.analyze_reply(
    subject="Re: Hello",
    body="Thanks! I'd like to learn more about pricing.",
    sender_email="john@example.com"
)
agent.close()
```

---

### 4. Follow-ups Agent

**File**: `app/services/followups.py` - `generate_followups()`

**Purpose**: Automatically create follow-up drafts based on sent email timeline

**Rules**:
- Day 3 follow-up: If original sent 3-4 days ago
- Day 5 follow-up: If original sent 5-7 days ago
- No follow-up after day 8

**Process**:
1. Query sent drafts with sent_at timestamps
2. Calculate days since original send
3. Check if contact already has follow-up drafts
4. Create new draft using follow-up template
5. Set status to "draft" (requires manual approval)

**Endpoint**: `POST /api/queue/followups`

---

### 5. AI Brain Agent

**File**: `app/agents.py` - `AIBrainAgent` class

**Purpose**: LLM-powered intelligence layer for email enhancement

**Configuration**:
```
NVIDIA_API_KEY=your-key
NVIDIA_MODEL=nvidia/nllama-3-70b
```

**Capabilities**:
- Subject line optimization
- Body content refinement  
- Tone adjustment
- Content summarization
- Action item extraction
- A/B test variant generation

**Example Usage**:
```python
from app.agents import AIBrainAgent

agent = AIBrainAgent()

# Enhance subject line
optimized = agent.enhance_subject("Quick question")

# Generate alternatives for A/B testing
alternatives = agent.generate_alternatives(
    subject="Quick question",
    body="I wanted to follow up...",
    count=3
)

# Summarize conversation
summary = agent.summarize_thread(messages=["msg1", "msg2"])

agent.close()
```

**Methods**:
```python
def enhance_subject(self, subject: str, context: Optional[Dict] = None) -> str
def enhance_body(self, body: str, style: str = "professional") -> str
def generate_alternatives(self, subject: str, body: str, count: int = 3) -> List[Dict[str, str]]
def summarize_thread(self, messages: List[str]) -> str
def extract_action_items(self, email_text: str) -> List[str]
```

---

### 6. Sender Agent

**File**: `app/agents.py` - `SenderAgent` class

**Purpose**: Handle email delivery through SMTP with proper error handling

**Safeguards**:
- Validates SMTP configuration before sending
- Never marks draft as "sent" if SMTP not configured
- Handles connection errors gracefully
- Provides async sending capability

**Example Usage**:
```python
from app.agents import SenderAgent
from app.db import SMTPConfig

# Get or create SMTP config
smtp = db.query(SMTPConfig).first()

agent = SenderAgent(smtp_config=smtp)

# Check if configured
if agent.is_configured():
    success, message, msg_id = agent.send(
        to_email="recipient@example.com",
        subject="Hello",
        body="Message body"
    )
```

**Methods**:
```python
def is_configured(self) -> bool
def validate_configuration(self) -> Tuple[bool, str]
def test_connection(self, timeout: int = 10) -> Tuple[bool, str]
def send(self, to_email: str, subject: str, body: str, ...) -> Tuple[bool, str, Optional[str]]
async def send_async(self, ...) -> Tuple[bool, str, Optional[str]]
```

---

### 7. Calendar Agent

**File**: `app/agents.py` - `CalendarAgent` class

**Purpose**: Meeting scheduling and calendar integration

**Supported Providers**:
- `google` - Google Calendar integration (stub)
- `microsoft` - Microsoft Graph API (stub)
- `calendly` - Calendly API (stub)
- `manual` - Manual scheduling (development mode)

**Example Usage**:
```python
from app.agents import CalendarAgent
from datetime import datetime, timezone

# Initialize for manual scheduling
agent = CalendarAgent(provider="manual")

# List available calendars
calendars = agent.list_calendars()

# Create an event
event = agent.create_event(
    summary="Demo Call",
    start_time=datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc),
    duration_minutes=30,
    attendees=["client@example.com"]
)

# Generate meeting link
link = agent.generate_meeting_link("call")
```

**Methods**:
```python
def list_calendars(self) -> List[Dict[str, Any]]
def create_event(self, summary, start_time, duration_minutes, ...) -> Dict[str, Any]
def generate_meeting_link(self, meeting_type: str = "call") -> str
def available(self) -> bool
```

---

### 8. Email Agent (Queue Manager)

**File**: `app/agents.py` - `QueueManager` class

**Purpose**: Orchestrate batch email sending with rate limiting

**Key Responsibilities**:
1. Monitor pending drafts (status: draft or blocked)
2. Enforce daily/weekly send limits
3. Apply pacing (minimum 60 seconds between sends)
4. Process drafts in order
5. Handle failures gracefully

**Methods**:
```python
class QueueManager:
    @property
    def alive(self) -> bool:
        """Check if scheduler is running"""
    
    @property
    def last_poll(self) -> Optional[float]:
        """Get last queue processing timestamp"""
    
    def process_queue(self) -> Dict[str, Any]:
        """Process all eligible pending drafts"""
        # Returns: {"processed": int, "sent": int, "failed": int, "skipped": int, "details": [...]}
```

**Scheduler Integration**:
```python
# Runs every 5 minutes only when AUTOPILOT=true AND AUTO_APPROVE=true
scheduler.add_job(
    queue_manager.process_queue,
    'interval',
    minutes=5,
    next_run_time=datetime.now()
)
```

---

### 9. Queue API Endpoints

**File**: `app/routers/queue.py`

The Queue API exposes endpoints for creating drafts and sending emails in batch.

#### Run All (Send to Selected Contacts)

**POST** `/api/queue/run-all`

Create drafts for specific contacts and process the queue to send emails.

**Request Body**:
```json
{
  "template_id": 1,
  "contact_ids": [1, 2, 3]
}
```

**Query Parameters**:
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| goal | string | No | - | Campaign goal description |
| template_id | int | No | First active template | Template to use for personalization |

**Response**:
```json
{
  "message": "Orchestration run-all completed",
  "goal": "Send emails to selected contacts",
  "template_used": "Welcome Email",
  "drafts_created": 3,
  "result": {
    "processed": 3,
    "sent": 3,
    "failed": 0,
    "skipped": 0,
    "details": [...]
  }
}
```

**Usage**: This endpoint is used by the UI's "Send Selected" dropdown button. When contacts are selected and a template is chosen from the dropdown, the frontend sends the contact IDs in the request body.

**Process**:
1. Finds contacts by ID (must have `eligible_to_email=true`)
2. Creates personalized drafts using the specified template
3. Processes the queue to send all drafts
4. Skips contacts that already have pending drafts

---

## Agent Factory

**Function**: `create_agent_for_task()`

Creates the appropriate agent for a given task type:

```python
from app.agents import create_agent_for_task

agent = create_agent_for_task("personalize", contact_id=1, template_id=5)
# Returns PersonalizedEmailAgent instance

agent = create_agent_for_task("send", smtp_config=smtp)
# Returns SenderAgent instance

agent = create_agent_for_task("calendar", provider="manual")
# Returns CalendarAgent instance
```

---

## Agent Communication Flow

```
User Request                    Backend Processing              External
    │                                │                              │
    │  POST /api/drafts/compose      │                              │
    ├────────────────────────────────►│                              │
    │                                ▼                              │
    │                         [Create Draft in DB]                 │
    │                                │                              │
    │  GET /api/queue/status         │                              │
    ├────────────────────────────────►│                              │
    │                                ▼                              │
    │                   [Process queue with limits check]          │
    │                   [Check contact eligibility]                │
    │                                │                              │
    │                     [PersonalizedEmailAgent.personalize()]   │
    │                     [expand_template_with_ai()]               │
    │                                │                              │
    │                   [QueueManager.process_queue()]             │
    │                                │                              │
    │                   [SenderAgent.send()]                       │
    │                   [via app/services/mailer.py SMTP]          │
    │                                │                              │
    │                   [Log event, update draft status]           │
    │                                │                              │
    │  GET /api/drafts?status=sent   │                              │
    ├────────────────────────────────►│                              │
```

---

## Error Handling

Each agent returns structured errors:
- Database errors → 500 Internal Server Error
- Validation errors → 400 Bad Request
- Rate limits → 200 with "paused" status
- SMTP errors → Specific error message in draft.error_message

---

## Testing

Agents are tested in:
- `tests/test_basic.py` - API integration tests
- `tests/test_send_limits.py` - Limits enforcement tests

---

## Implementation Status

| Agent | Status | File |
|-------|--------|------|
| Email Orchestrator Base | ✅ Complete | `app/agents.py` |
| Personalized Email Agent | ✅ Complete | `app/agents.py` |
| Reply Analyzer Agent | ✅ Complete | `app/agents.py` |
| Follow-ups Agent | ✅ Complete | `app/services/followups.py` |
| AI Brain Agent | ✅ Complete | `app/agents.py` |
| Sender Agent | ✅ Complete | `app/agents.py` |
| Calendar Agent | ✅ Complete (stub) | `app/agents.py` |
| Queue Manager | ✅ Complete | `app/agents.py` |

---

## API Endpoints

All agents are exposed via REST API endpoints under `/api/agents/`:

| Endpoint | Method | Agent | Purpose |
|----------|--------|-------|---------|
| `/personalize` | POST | PersonalizedEmailAgent | Personalize email for contact |
| `/send` | POST | SenderAgent | Send email directly |
| `/test-smtp` | GET | SenderAgent | Test SMTP connection |
| `/calendar` | GET | CalendarAgent | List calendars |
| `/calendar/event` | POST | CalendarAgent | Create calendar event |
| `/brain/enhance-subject` | POST | AIBrainAgent | Optimize subject line |
| `/brain/enhance-body` | POST | AIBrainAgent | Improve email body |
| `/brain/alternatives` | POST | AIBrainAgent | Generate A/B variations |
| `/brain/summarize` | POST | AIBrainAgent | Summarize thread |
| `/brain/action-items` | POST | AIBrainAgent | Extract action items |
| `/status` | GET | - | Get all agent statuses |

### Queue API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/queue/status` | GET | Get queue status and pending drafts |
| `/api/queue/run` | POST | Run one queue pass (process drafts) |
| `/api/queue/run-all` | POST | Create drafts for selected contacts and send |
| `/api/queue/followups` | POST | Generate follow-up drafts |

### Quick API Examples

**Personalize an email:**
```bash
curl -X POST "http://127.0.0.1:8000/api/agents/personalize?contact_id=1&template_id=5&use_ai=true"
```

**Send email directly:**
```bash
curl -X POST "http://127.0.0.1:8000/api/agents/send?to_email=user@example.com&subject=Hello&body=Message"
```

**Enhance subject with AI:**
```bash
curl -X POST "http://127.0.0.1:8000/api/agents/brain/enhance-subject?subject=Quick%20question"
```

**Generate A/B alternatives:**
```bash
curl -X POST "http://127.0.0.1:8000/api/agents/brain/alternatives?subject=Hello&body=Message&count=3"
```

**Check agent status:**
```bash
curl http://127.0.0.1:8000/api/agents/status
```

See [API_REFERENCE.md](API_REFERENCE.md) for complete API documentation.