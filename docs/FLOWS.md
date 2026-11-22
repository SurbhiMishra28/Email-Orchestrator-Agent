# Core Flows

End-to-end behaviour of the orchestrator: who calls what, which gates apply, and
where state is written. Every flow below is tenant-scoped — `tenant_id` is resolved
from the JWT (or the implicit local tenant when `SINGLE_USER_MODE=true`) and applied
to every query, insert and update.

## 1. Request lifecycle

Every API call passes through the same gate chain before touching business logic.

```mermaid
flowchart TD
    A[Browser / API client] --> B{Path protected?}
    B -- "/api/track/* , /api/auth/* , /health" --> C[Public handler]
    B -- everything else --> D{SINGLE_USER_MODE}
    D -- true --> E[Resolve implicit Local tenant]
    D -- false --> F{Bearer token valid?}
    F -- no --> G[401 Unauthorized]
    F -- yes --> H[Decode sub + tenant_id]
    E --> I[Rate limiter key = tenant:id]
    H --> I
    I --> J{Route limit exceeded?}
    J -- yes --> K[429 Too Many Requests]
    J -- no --> L[Handler runs tenant-scoped query]
    L --> M[Response]
```

Sources: `app/auth.py`, `app/deps.py`, `app/main.py` (`_rate_limit_key`, `limiter`).

## 2. Contact import

```mermaid
flowchart TD
    A["POST /api/contacts/import<br/>{csv: string}"] --> B[Parse header row]
    B --> C{Valid email?}
    C -- no --> D[Append to errors]
    C -- yes --> C2{Mailable address?}
    C2 -- no --> D
    C2 -- yes --> E{Contact exists in tenant?}
    E -- no --> F[Create contact<br/>imported += 1]
    E -- yes --> G[Refresh name/company/role/<br/>phone/linkedin/notes<br/>updated += 1]
    F --> H[Collect eligible emails]
    G --> H
    H --> I{Autopilot AND Auto-approve?}
    I -- yes --> J[Queue background intro outreach]
    I -- no --> K[Stop at drafts]
    J --> L[Write Log + return counts]
    K --> L
```

The response reports `imported`, `updated`, `skipped` and `errors` as mutually
exclusive buckets, so a re-import of the same file returns `imported: 0`.

Eligibility is opt-in: a contact is only mailable when `eligible_to_email` is true,
which requires `email_permission=true` in the CSV (or the toggle in the UI).

The second gate (`C2`) is `services/recipients.blocked_reason`: reserved domains
(`example.com`, `*.test`, `localhost`), disposable inboxes and mail-system
mailboxes are rejected with a reason in `errors`, so a placeholder row can never
become an autopilot target. `BLOCK_PLACEHOLDER_RECIPIENTS=false` disables it.

## 3. Draft and send pipeline

```mermaid
flowchart TD
    A["POST /api/drafts/compose"] --> B[PersonalizedEmailAgent]
    B --> C[Expand template variables<br/>+ optional AI enhancement]
    C --> D[Save Draft status=draft]
    D --> E[record_usage: emails_drafted]
    E --> F{Send path}
    F -- manual --> G["POST /api/drafts/{id}/send"]
    F -- queue --> H["POST /api/queue/run"]
    H --> I[QueueManager.process_queue]
    I --> I2{Blacklisted or<br/>placeholder recipient?}
    G --> I2
    I2 -- yes --> I3[status=failed<br/>no SMTP call]
    I2 -- no --> J{Limits check}
    J --> K[Warm-up cap]
    J --> L[DAILY_CAP]
    J --> M[Plan limit]
    J --> N[Recipient-domain cap]
    K --> O{Lowest cap reached?}
    L --> O
    M --> O
    N --> O
    O -- yes --> P[status=blocked<br/>no SMTP call]
    O -- no --> Q[SenderAgent.send]
    Q --> R{SMTP ok?}
    R -- yes --> S[status=sent + sent_at<br/>record_usage: emails_sent]
    R -- no --> T[status=failed + error_message]
```

The effective cap is `min(warm-up, DAILY_CAP, plan_limit, domain cap)` — see
`app/services/limits.py`. A draft never flips to `sent` unless SMTP actually
accepted the message.

Both send paths also refuse a recipient that cannot receive mail (see
`services/recipients.blocked_reason`) and a contact blacklisted by a bounce. Such
a draft becomes `failed` with the reason in `error_message`, so it is not retried
on the next pass.

## 4. Reply detection and auto-response

```mermaid
sequenceDiagram
    participant SCH as Scheduler
    participant IB as Inbox service
    participant DB as Database
    participant RA as ReplyAnalyzerAgent
    participant AR as AutoResponder
    participant SMTP as SMTP relay

    SCH->>IB: poll (IMAP_POLL_MINUTES)
    IB->>IA: fetch read-only (BODY.PEEK)
    IA-->>IB: new messages
    IB->>DB: store InboxMessage
    IB->>RA: classify reply
    RA-->>IB: type, sentiment, confidence
    IB->>DB: Event reply_received (+ tenant_id)
    IB->>DB: record_usage replies_received
    alt reply type has a response template
        IB->>AR: compose response
        AR->>DB: Draft (message_kind=auto_reply)
        AR->>SMTP: send
        SMTP-->>AR: accepted
        AR->>DB: Draft status=sent
    else spam / acknowledgement
        IB->>DB: record classification only, no answer
    end
```

Inbox polling is read-only and never marks mail as read. Follow-up drafting stops
for any contact that has replied.

Nothing in this path waits for a human. `AutoResponder.RESPONSE_TEMPLATES` only
covers `positive_response`, `question` and `schedule_call`, so a negative, spam or
acknowledgement reply is classified and stored but never answered.

### Delivery failures

```mermaid
flowchart TD
    A[InboxMessage] --> B{mailer-daemon / postmaster sender<br/>+ DSN marker?}
    B -- no --> C[Normal reply path]
    B -- yes --> D[Extract failed address from the DSN]
    D --> E[Contact: email_blacklisted=true, eligible_to_email=false]
    E --> F[Outstanding drafts -> failed]
    F --> G[Campaign.bounced += 1]
    G --> H[Log warning; never auto-reply]
```

A bounce is the only hard evidence that a mailbox is dead, because the relay
accepts the message before it knows. Once blacklisted, the contact is excluded
from intro drafting, queue selection and every direct send, and existing drafts
are failed rather than retried. Detection requires a daemon sender *and* a DSN
marker, so a prospect writing "your message wasn't delivered" is not mistaken for
a bounce.

## 5. Follow-up scheduling

```mermaid
flowchart LR
    A[Sent draft at T0] --> B{Days since send}
    B -- "3-4" --> C[Day-3 follow-up draft]
    B -- "5-7" --> D[Day-5 follow-up draft]
    B -- "> 8" --> E[Stop]
    C --> F{Reply received?}
    D --> F
    F -- yes --> E
    F -- no --> G[Draft status=draft<br/>sent by the same queue pass]
```

Follow-ups create drafts only — the queue sends them on its next pass, so no manual
approval step exists. `FOLLOWUPS_ENABLED=false` disables the whole stage.

## 6. Engagement tracking (opt-in, off by default)

```mermaid
flowchart TD
    A[Tenant enables tracking_enabled] --> B{Draft is auto_reply?}
    B -- yes --> C[Never tracked]
    B -- no --> D[Build multipart/alternative]
    D --> E[Plain-text body unchanged]
    D --> F[HTML part + 1x1 pixel]
    D --> G[Links rewritten to /api/track/click/token]
    F --> H[GET /api/track/open/token]
    G --> I[GET /api/track/click/token?url=...]
    H --> J[Verify HMAC token]
    I --> J
    J -- invalid --> K[Record nothing]
    J -- valid --> L[Event email_opened / link_clicked]
    I --> M[302 to absolute http s target only]
```

Tokens are signed HMACs over draft and tenant id, so a public endpoint cannot
attribute an open or click to another tenant. With tracking disabled, outbound mail
is plain text with no HTML part at all.

## 7. A/B experiments

```mermaid
flowchart TD
    A[Create ABTest + variants<br/>labels, weights] --> B{Weights valid?}
    B -- "duplicate labels or all zero" --> C[400 rejected]
    B -- ok --> D[Active test for tenant]
    D --> E["POST run-all<br/>contact_ids"]
    E --> F[Deterministic weighted assignment per contact]
    F --> G[Draft records experiment + variant]
    G --> H[Send path as normal]
    H --> I[Events: sent / opened / clicked / replied]
    I --> J[Per-variant results]
```

Assignment is deterministic per contact, so re-running does not shuffle variants
between sends.

## 8. Usage metering and plan limits

```mermaid
flowchart LR
    A[emails_drafted] --> D[usage_logs]
    B[emails_sent] --> D
    C[replies_received] --> D
    D --> E["GET /api/usage<br/>(today + month)"]
    D --> F["/api/state.usage"]
    E --> G[UI: Sent today X / cap]
    F --> G
    G --> H{At cap?}
    H -- yes --> I[Send blocked with<br/>"Plan limit reached" ]
    H -- no --> J[Sending continues]
```

Three counters are recorded at the moment of the action, not derived afterwards:
drafting, sending, and reply receipt. The Overview progress bar turns red at the cap.

## 9. Tenant provisioning and isolation

```mermaid
flowchart TD
    A[Register or first run] --> B{Existing tenant?}
    B -- no --> C[Create Tenant]
    B -- yes --> D[Reuse]
    C --> E[Create owner User]
    D --> E
    E --> F[Create Settings + SMTPConfig]
    F --> G[Seed default templates]
    G --> H[Every row stamped tenant_id]
    H --> I[All queries filter tenant_id]
    I --> J[Cross-tenant ID access returns 404]
```

In single-user mode the lifespan hook provisions one `Local` tenant and adopts any
legacy rows whose `tenant_id` is NULL.

## 10. Live agent activity stream

```mermaid
sequenceDiagram
    participant UI as LiveAgentActivity
    participant WS as /ws/live-logs
    participant AG as Agent method

    UI->>WS: connect
    WS-->>UI: streaming
    AG->>WS: agent_started (run id, name)
    WS-->>UI: event appended (60 cap)
    alt method raises
        AG->>WS: agent_failed (reason)
    else returns False / success=false
        AG->>WS: agent_failed (reason)
    else success
        AG->>WS: agent_completed
    end
    Note over UI,WS: reconnect with backoff to 30s
```

Outcome classification lives in `app/live_logs.py::_outcome`, so a tuple of
`(False, reason)` or a dict `{"success": False}` reports `failed`, not `completed`.
