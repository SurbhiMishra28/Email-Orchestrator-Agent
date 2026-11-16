# Email Orchestrator Examples

This document provides practical examples for using the Email Orchestrator.

## 1. Creating a Contact

```python
import httpx

response = httpx.post('http://127.0.0.1:8000/api/contacts', json={
    "email": "jane.doe@acme.com",
    "name": "Jane Doe",
    "company": "Acme Corp",
    "role": "CTO",
    "industry": "Software",
    "eligible_to_email": True
})

print(response.json())
# {"id": 1, "email": "jane.doe@acme.com", "name": "Jane Doe", ...}
```

## 2. Creating an Email Template

```bash
curl -X POST http://127.0.0.1:8000/api/templates \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Intro Email - Software",
    "category": "intro",
    "subject_template": "Quick intro from {{business_name}} about {{goal}}",
    "body_template": "Hi {{first_name}},\n\nI\'m {{sender_name}} from {{business_name}}. We help {{company}} like yours with {{business_offer}}.\n\nWould you be open to a 15-minute call this week?\n\nBest regards,\n{{sender_name}}"
  }'
```

## 3. Composing and Sending an Email

```python
import httpx

# Step 1: Create a draft
draft_response = httpx.post('http://127.0.0.1:8000/api/drafts/compose', json={
    "contact_id": 1,
    "subject": "Quick question about your workflow",
    "body": "Hi Jane,\n\nI noticed you\'re based at Acme Corp. We help companies like yours streamline their operations with our automation platform.\n\nWould you be open to a quick 15-minute call?\n\nBest,\nAlex"
})

draft = draft_response.json()
print(f"Draft created: {draft['id']}")

# Step 2: Get queue status
queue = httpx.get('http://127.0.0.1:8000/api/queue/status').json()
print(f"Pending drafts: {queue['pending_drafts']}")

# Step 3: Run the queue (if AUTOPILOT and AUTO_APPROVE are enabled)
# Or manually send the draft:
send_response = httpx.post(f'http://127.0.0.1:8000/api/drafts/{draft["id"]}/send')
print(f"Send status: {send_response.json()}")
```

## 4. Using a Template with Personalization

```python
# Use template to create a personalized draft
response = httpx.post('http://127.0.0.1:8000/api/templates/use', json={
    "template_id": 1,
    "contact_id": 1,
    "use_ai": True  # Use AI for additional personalization
})

draft = response.json()
print(f"Subject: {draft['subject']}")
print(f"Body preview: {draft['body'][:200]}...")
```

## 5. Analyzing an Email Reply

```python
response = httpx.post('http://127.0.0.1:8000/api/replies/analyze', json={
    "subject": "Re: Quick question",
    "body": "Thanks for reaching out! I\'m interested in learning more about your platform. Can you send me some pricing information?",
    "sender_email": "jane.doe@acme.com",
    "contact_id": 1
})

result = response.json()
print(f"Reply type: {result['reply_type']}")  # positive_response
print(f"Confidence: {result['confidence']}")  # 0.95
print(f"Suggested action: {result['suggested_action']}")  # send_proposal
```

## 6. Importing Contacts from CSV

```python
csv_content = """email,name,company,role,industry,eligible_to_email
john.smith@tech.com,John Smith,Tech Solutions,CEO,Technology,true
alice.wong@startup.io,Alice Wong,Startup.io,CTO,Technology,true
"""

files = {'file': ('contacts.csv', csv_content, 'text/csv')}
response = httpx.post('http://127.0.0.1:8000/api/contacts/import', files=files)

result = response.json()
print(f"Imported: {result['imported']}")
print(f"Failed: {result['failed']}")
```

## 7. Setting Up SMTP

```python
import httpx

response = httpx.post('http://127.0.0.1:8000/api/smtp/config', json={
    "host": "smtp.gmail.com",
    "port": 587,
    "user": "youremail@gmail.com",
    "password": "your-app-password",
    "sender": "Your Name"
})

print(response.json())
# {"host": "smtp.gmail.com", "configured": true, ...}

# Test the connection
test_response = httpx.post('http://127.0.0.1:8000/api/smtp/test')
print(test_response.json())  # {"success": true}
```

## 8. Creating Follow-ups

```python
# Generate follow-up drafts for sent emails
response = httpx.post('http://127.0.0.1:8000/api/queue/followups')

result = response.json()
print(f"Created: {result['created']} follow-ups")
print(f"Skipped: {result['skipped']} already have follow-ups")
```

## 9. Verifying Email Addresses

```python
# Single email verification
response = httpx.post('http://127.0.0.1:8000/api/verifications/check', json={
    "email": "jane.doe@acme.com"
})

result = response.json()
print(f"Status: {result['status']}")  # deliverable, risky, undeliverable
print(f"SMTP check: {result['smtp_check']}")
print(f"MX check: {result['mx_check']}")
```

## 10. Bulk Email Verification

```python
# Start bulk verification job
response = httpx.post('http://127.0.0.1:8000/api/verifications/bulk', json={
    "contact_ids": [1, 2, 3, 4, 5],
    "check_smtp": True,
    "check_catch_all": True
})

job = response.json()
job_id = job['job_id']
print(f"Job started: {job_id}")

# Poll for completion
import time
time.sleep(5)  # Wait for processing

status = httpx.get(f'http://127.0.0.1:8000/api/verifications/bulk/{job_id}').json()
print(f"Processed: {status['processed']}/{status['total']}")
print(f"Deliverable: {status['deliverable']}")
```

## 11. Sync Inbox

```python
# Fetch latest emails from IMAP
response = httpx.post('http://127.0.0.1:8000/api/inbox/sync?limit=10')

result = response.json()
print(f"Synced: {result['synced']} new messages")
print(f"Total stored: {result['total_stored']}")
```

## 12. Get Application State

```python
response = httpx.get('http://127.0.0.1:8000/api/state')
state = response.json()

print(f"Contacts: {len(state['contacts'])}")
print(f"Drafts: {len(state['drafts'])}")
print(f"Settings: {state['settings']}")
```

---

## Using the Python SDK (Direct API Access)

```python
from app.agents import PersonalizedEmailAgent, SenderAgent, ReplyAnalyzerAgent, create_agent_for_task
from app.db import SessionLocal, Contact, Template, SMTPConfig

# Create database session
db = SessionLocal()

# Use factory to create agents
personalizer = create_agent_for_task("personalize", contact_id=1, template_id=1)
result = personalizer.personalize(use_ai=True)

sender = create_agent_for_task("send", smtp_config=db.query(SMTPConfig).first())
if sender.is_configured():
    success, msg, msg_id = sender.send("test@example.com", "Subject", "Body")

# Direct reply analysis
analyzer = create_agent_for_task("reply", contact_id=1)
analysis = analyzer.analyze_reply("Subject", "Body", "sender@example.com")
analyzer.close()

db.close()
```

---

## Working with Drafts

```python
from app.agents import QueueManager

# Process all pending drafts
queue = QueueManager()
results = queue.process_queue()

print(f"Sent: {results['sent']}")
print(f"Failed: {results['failed']}")
print(f"Skipped: {results['skipped']}")
for detail in results.get('details', []):
    print(f"  {detail}")
```