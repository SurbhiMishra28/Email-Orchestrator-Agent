# Feature Inventory

What exists today, where it lives, and how it is verified. Status reflects the
current codebase, not a roadmap.

Legend: **Done** = implemented and covered by tests. **Done (stub)** = wired end to
end but the external integration is a placeholder. **Not built** = planned only.

## Audience

| Feature | Status | Backend | Frontend | Verified by |
|---|---|---|---|---|
| Contact list with search | Done | `app/routers/contacts.py` | Contacts view | `test_contacts_probe.py` |
| Create / edit / delete contact | Done | `contacts.py` | Contacts view | `test_contacts_probe.py` |
| CSV import with upsert | Done | `contacts.py::import_csv` | Import CSV button | `test_contacts_ui_contract.py` |
| Opt-in eligibility toggle | Done | `contacts.py` | SUBSCRIBED badge | `test_contacts_probe.py` |
| Bulk delete | Done | `contacts.py::/bulk` | row selection + header select-all | `test_contacts_probe.py` |
| Tags per contact | Done | `contacts.py` tag routes | API only | `test_contacts_ui_contract.py` |
| Contact lists (segments) | Done | `app/routers/lists.py` | Contacts sidebar | `test_lists.py` |
| List folders | Done | `lists.py/folders` | folder filter | `test_lists.py` |
| List import / duplicate / merge | Done | `lists.py` | list actions menu | `test_lists.py` |
| Per-list settings, header, footer | Done | `lists.py/settings` | List settings modal | `test_lists.py` |

## Campaigns and sending

| Feature | Status | Backend | Frontend | Verified by |
|---|---|---|---|---|
| Templates CRUD | Done | `app/routers/templates.py` | Templates view | `test_basic.py` |
| Template variable expansion | Done | `templates.py/expand` | Templates view | `test_basic.py` |
| Draft compose | Done | `app/routers/drafts.py` | Drafts view | `test_usage.py` |
| Manual send | Done | `drafts.py/{id}/send` | Send button | `test_usage.py` |
| Queue run (paced) | Done | `app/routers/queue.py` | Automation view | `test_send_limits.py` |
| Async send queue | Done | `app/services/send_worker.py` | Queue status | `test_async_sending.py` |
| Campaigns CRUD | Done | `app/routers/campaigns.py` | Campaigns view | `test_campaigns.py` |
| Campaign pause / cancel / duplicate | Done | `campaigns.py` | Campaigns view | `test_campaigns.py` |
| Campaign stats | Done | `campaigns.py/{id}/stats` | Campaigns view | `test_campaigns.py` |
| A/B experiments | Done | `app/routers/ab_tests.py` | Experiments view | `test_ab_testing.py` |
| Reply classification | Done | `app/routers/replies.py` | Agents view | `test_auto_replies.py` |
| Auto-response sending | Done | `app/agents.py` AutoResponder | Agents view | `test_auto_replies.py` |

## Deliverability

| Feature | Status | Backend | Frontend | Verified by |
|---|---|---|---|---|
| SMTP config + test | Done | `app/routers/smtp.py` | Settings view | `test_basic.py` |
| IMAP inbox sync (read-only) | Done | `app/routers/inbox.py` | Inbox view | `test_basic.py` |
| Follow-up drafting (day 3/5) | Done | `app/services/followups.py` | Automation view | `test_followups.py` |
| Email verification | Done | `app/routers/verifications.py` | Verifications view | `test_verification.py` |
| Bulk verification jobs | Done | `verifications.py/bulk` | Verifications view | `test_verification.py` |
| Warm-up caps | Done | `app/services/limits.py` | Usage bar | `test_send_limits.py` |
| Open / click tracking (opt-in) | Done | `app/routers/track.py` | Settings toggle | `test_engagement_tracking.py` |
| Tracking attribution display | Done | `app/routers/tracking.py` | Tracking panel | `test_tracking.py` |

## Platform

| Feature | Status | Backend | Frontend | Verified by |
|---|---|---|---|---|
| Multi-tenancy | Done | `app/db.py`, `app/deps.py` | — | `test_tenant_isolation.py` |
| JWT auth + refresh | Done | `app/routers/auth.py` | Auth screen | `test_tenant_isolation.py` |
| Single-user mode | Done | `app/config.py`, `app/auth.py` | — | `test_basic.py` |
| Team members + invites | Done | `app/routers/tenants.py` | Team view | `test_teams.py` |
| API keys | Done | `auth.py/api-keys` | — | `test_tenant_isolation.py` |
| Usage metering | Done | `app/services/usage.py` | Overview bar | `test_usage.py` |
| Analytics | Done | `app/main.py::_build_analytics` | Overview | `test_basic.py` |
| Live agent stream | Done | `app/live_logs.py` | Agents view | `test_agent_tracking.py` |
| Scheduler status | Done | `app/routers/scheduling.py` | Automation view | `test_scheduling.py` |
| Per-tenant rate limiting | Done | `app/main.py::_rate_limit_key` | — | `test_tenant_isolation.py` |
| URL routing / deep links | Done | — | `App.jsx` | manual |
| Mobile drawer navigation | Done | — | `App.jsx`, `index.css` | manual |

## Integrations

| Integration | Status | Notes |
|---|---|---|
| SMTP (any relay) | Done | Requires real credentials; blocked until configured |
| IMAP inbox | Done | Read-only via `BODY.PEEK` |
| NVIDIA LLM | Done | Optional; templates used when no key |
| Calendly | Done | Shares the booking link saved in Settings |
| Google Calendar | Not built | No OAuth flow |
| Microsoft Graph | Not built | No OAuth flow |
| Stripe billing | Not built | Roadmap only |

## Known gaps

- SMTP and IMAP cannot be exercised in an offline environment; those paths are
  covered by configuration checks, not live network calls.
- Calendar integration stops at link sharing: there is no OAuth, no event
  creation and no calendar sync.
- Billing, plan upgrades and invoicing are not implemented. `plan_daily_limit`
  reads a plan field but there is no purchase flow.
- Open/click tracking conflicts with the README's historical "no tracking pixels"
  stance; it is shipped but off by default.
