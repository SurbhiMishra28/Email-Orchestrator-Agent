"""Email agent orchestration and template expansion."""
import asyncio
import json
import logging
import os
import re
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from jinja2 import Template as JinjaTemplate
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ``langchain_core`` messages are cheap to import and are used throughout, so
# they stay at module scope; only the heavy provider SDKs are lazy (below).
from langchain_core.messages import HumanMessage, SystemMessage

from app.db import SessionLocal, Contact, Draft, Template, Log, ToolUse, Settings, Event, SMTPConfig
from app.live_logs import instrument_agent
from app.services.limits import check_send_allowed
from app.services.mailer import (
    MailDeliveryError,
    MailNotConfigured,
    is_configured,
    sender_address,
    send_email,
)
from app.services.recipients import blocked_reason
from app.services.usage import EMAILS_SENT, REPLIES_RECEIVED, record_usage

# ``langchain_nvidia_ai_endpoints`` costs more import time than the rest of the
# application put together, and it is only needed when a draft is actually
# personalised. Importing it at module scope therefore taxed every cold start
# and every request on a serverless host. It is loaded on first use and cached.
_chat_nvidia_cls = None
_chat_nvidia_loaded = False


def _chat_nvidia_class():
    """Return ChatNVIDIA, importing it on first use (or None if unavailable)."""
    global _chat_nvidia_cls, _chat_nvidia_loaded
    if not _chat_nvidia_loaded:
        _chat_nvidia_loaded = True
        try:
            from langchain_nvidia_ai_endpoints import ChatNVIDIA

            _chat_nvidia_cls = ChatNVIDIA
        except ImportError:  # optional dependency
            _chat_nvidia_cls = None
    return _chat_nvidia_cls


@dataclass
class TemplateVariables:
    """Context variables available for template expansion."""
    company: str = ""
    first_name: str = ""
    last_name: str = ""
    role: str = ""
    industry: str = ""
    goal: str = ""
    business_name: str = ""
    business_offer: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def expand_template_variables(template_str: str, variables: Dict[str, Any]) -> str:
    """Expand Jinja2-style template variables in a string."""
    try:
        template = JinjaTemplate(template_str)
        return template.render(**variables)
    except Exception as e:
        return f"{{Error expanding template: {e}}}"


def _render_footer(template, variables: Dict[str, Any]) -> str:
    """Render a template's footer with the same variables as the body.

    Templates store the footer as a Jinja2 string (``{{sender_name}}`` and
    friends), so it has to be expanded before it is appended. Appending the
    raw string shipped literal placeholders to recipients.
    """
    footer = (getattr(template, "footer_template", "") or "").strip()
    if footer:
        return expand_template_variables(footer, variables).strip()
    return (variables.get("footer_text") or "").strip()


def neon_gateway_configured() -> bool:
    from app.config import settings as app_settings

    return bool(
        (app_settings.NEON_AI_GATEWAY_BASE_URL or "").strip()
        and (app_settings.NEON_AI_GATEWAY_TOKEN or "").strip()
    )


def default_alias(db, tenant_id, draft=None) -> tuple:
    """The sender identity to use as ``(name, email)``, or ``("", "")``.

    A draft can pin its own sender in ``variables`` (``from_email`` /
    ``from_name``), which is how a campaign's chosen alias reaches the queue.
    Otherwise the tenant's default alias is used.

    Sending resolves the From identity here so the alias list in Settings is not
    decorative: without this the queue would keep using the mailbox's own
    address and "Make default" would change nothing.
    """
    from app.db import EmailAlias

    if draft is not None:
        variables = getattr(draft, "variables", None) or {}
        pinned_email = (variables.get("from_email") or "").strip()
        if pinned_email:
            return (variables.get("from_name") or "").strip(), pinned_email

    if tenant_id is None:
        return "", ""
    alias = (
        db.query(EmailAlias)
        .filter(
            EmailAlias.tenant_id == tenant_id,
            EmailAlias.is_default.is_(True),
            EmailAlias.is_active.is_(True),
        )
        .order_by(EmailAlias.id.asc())
        .first()
    )
    if alias is None or not alias.email:
        return "", ""
    return (alias.name or "").strip(), alias.email.strip()


def get_neon_gateway_client():
    """An OpenAI-compatible client for the Neon AI Gateway, or None.

    ``NEON_AI_GATEWAY_BASE_URL`` is the bare branch host, so the OpenAI dialect
    path is appended here; ``ChatOpenAI`` then adds ``/chat/completions``.

    Returns None (rather than raising) when the gateway is not configured, so
    callers can fall back. When ``LLM_PROVIDER=neon`` that fallback is skipped
    explicitly -- a configured-but-broken gateway should not silently degrade to
    templates.
    """
    from app.config import settings as app_settings

    if not neon_gateway_configured():
        return None

    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.warning(
            "langchain-openai is not installed; the Neon AI Gateway is unavailable."
        )
        return None

    base_url = app_settings.NEON_AI_GATEWAY_BASE_URL.rstrip("/")
    try:
        return ChatOpenAI(
            model=app_settings.NEON_AI_GATEWAY_MODEL,
            api_key=app_settings.NEON_AI_GATEWAY_TOKEN,
            base_url=f"{base_url}/v1",
            temperature=0.7,
            timeout=60,
        )
    except Exception as e:
        logger.warning(f"Could not initialize the Neon AI Gateway client: {e}")
        return None


def get_llm_client():
    """Get the configured LLM client, or None when no provider is available.

    ``LLM_PROVIDER`` selects the backend:

    * ``auto``   -- NVIDIA when a key is configured, otherwise the Neon AI
      Gateway. NVIDIA stays first because it is the provider this app was built
      and tuned against; the gateway is the fallback, not a replacement.
    * ``nvidia`` -- NVIDIA only.
    * ``neon``   -- Neon AI Gateway only.

    An explicit provider never silently falls through to another, so a
    misconfigured deployment is visible instead of quietly returning templates.
    """
    from app.config import settings as app_settings

    provider = (app_settings.LLM_PROVIDER or "auto").lower()

    if provider == "neon":
        client = get_neon_gateway_client()
        if client is None:
            logger.warning(
                "LLM_PROVIDER=neon but the Neon AI Gateway is not configured "
                "(set NEON_AI_GATEWAY_BASE_URL and NEON_AI_GATEWAY_TOKEN)."
            )
        return client

    api_key = app_settings.NVIDIA_API_KEY
    model = app_settings.NVIDIA_MODEL

    chat_nvidia = _chat_nvidia_class()

    if api_key and chat_nvidia is not None:
        try:
            return chat_nvidia(model=model, api_key=api_key, temperature=0.7)
        except Exception as e:
            logger.warning(f"Could not initialize NVIDIA LLM: {e}")

    if provider == "nvidia":
        if not api_key:
            logger.warning("LLM_PROVIDER=nvidia but NVIDIA_API_KEY is not set.")
        return None

    # auto, with NVIDIA unavailable or uninitialised.
    client = get_neon_gateway_client()
    if client is None:
        if api_key:
            logger.warning(
                "langchain-nvidia-ai-endpoints is not installed; "
                "using the template engine."
            )
        return None
    return client


async def expand_template_with_ai(template: Template, contact: Contact, custom_values: Dict[str, Any] = None) -> Dict[str, str]:
    """Expand a template using AI for personalization."""
    db = SessionLocal()
    try:
        # Get the tenant's settings for context. The template and contact carry
        # the tenant, and the template's own tenant is authoritative.
        settings_query = db.query(Settings)
        tenant_id = getattr(template, "tenant_id", None) or getattr(contact, "tenant_id", None)
        if tenant_id is not None:
            settings_query = settings_query.filter(Settings.tenant_id == tenant_id)
        settings_row = settings_query.first()
        settings = {
            "goal": settings_row.goal if settings_row else "",
            "business_name": settings_row.business_name if settings_row else "",
            "business_offer": settings_row.business_offer if settings_row else "",
            "footer_text": settings_row.footer_text if settings_row else "",
            "sender_name": settings_row.sender_name if settings_row else "",
            "sender_role": settings_row.sender_role if settings_row else "",
            "company_website": settings_row.company_website if settings_row else "",
        }
        
        variables = {
            "company": contact.company or "",
            "first_name": (contact.name or "").split()[0] if contact.name else "",
            "last_name": " ".join((contact.name or "").split()[1:]) if contact.name and len((contact.name or "").split()) > 1 else "",
            "role": contact.role or "",
            "industry": contact.industry if hasattr(contact, 'industry') else "",
            "goal": settings.get("goal", ""),
            "business_name": settings.get("business_name", ""),
            "business_offer": settings.get("business_offer", ""),
            "footer_text": settings.get("footer_text", ""),
            "sender_name": settings.get("sender_name", ""),
            "sender_role": settings.get("sender_role", ""),
            "company_website": settings.get("company_website", ""),
            "calendly_url": settings_row.calendly_url if settings_row else "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "contact_email": contact.email,
        }
        if custom_values:
            variables.update(custom_values)
        
        # Try AI expansion first if LLM is available
        llm = get_llm_client()
        if llm:
            try:
                messages = [
                    SystemMessage(
                        content=(
                            "You are an email personalization assistant. Expand the "
                            "template subject and body with personalized content."
                        )
                    ),
                    HumanMessage(
                        content=f"""Subject Template: {template.subject_template}
Body Template: {template.body_template}
Footer Template: {template.footer_template or 'None - use global footer_text variable'}
Contact: {contact.name}, {contact.company}, {contact.role}
Variables: {json.dumps(variables, indent=2)}

Reply with a single JSON object and nothing else, using the shape
{{"subject": "...", "body": "..."}}. Keep the subject concise and the body professional."""
                    ),
                ]
                result = await asyncio.to_thread(llm.invoke, messages)
                content = result.content if hasattr(result, "content") else str(result)

                if isinstance(content, dict):
                    data = content
                else:
                    text = str(content).strip()
                    if text.startswith("```"):
                        text = text.strip("`")
                        if text.lower().startswith("json"):
                            text = text[4:]
                        text = text.strip()
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        data = None

                if isinstance(data, dict) and data.get("subject") and data.get("body"):
                    # Append footer if not already included and template has footer
                    body = data["body"]
                    footer = _render_footer(template, variables)
                    if footer and not body.rstrip().endswith(footer):
                        body = f"{body.rstrip()}\n\n{footer}"
                    return {"subject": data["subject"], "body": body}
                logger.warning("AI expansion returned an unusable response; using the template engine.")
            except Exception as e:
                logger.warning(f"AI expansion failed, using template engine: {e}")

        # Fallback to template engine
        body = expand_template_variables(template.body_template, variables)

        # Append footer if template has one
        footer = _render_footer(template, variables)
        if footer:
            body = f"{body.rstrip()}\n\n{footer}"

        return {
            "subject": expand_template_variables(template.subject_template, variables),
            "body": body
        }
    finally:
        db.close()


@instrument_agent
class EmailAgent:
    """Orchestrates email sending workflow."""
    
    def __init__(self, contact_id: int, template_id: int, smtp_config: Optional[Dict] = None):
        self.contact_id = contact_id
        self.template_id = template_id
        self.smtp_config = smtp_config
        self.db = SessionLocal()
    
    async def run(self, auto_approve: bool = True, send_via_smtp: bool = True) -> Dict[str, Any]:
        """Execute the email agent workflow."""
        try:
            # Get contact
            contact = self.db.query(Contact).filter(Contact.id == self.contact_id).first()
            if not contact:
                return {"success": False, "error": "Contact not found"}
            
            if not contact.eligible_to_email:
                return {"success": False, "error": "Contact not eligible for email"}
            
            # Get template
            template = self.db.query(Template).filter(Template.id == self.template_id, Template.is_active == True).first()
            if not template:
                return {"success": False, "error": "Template not found or inactive"}
            
            # Expand template
            expanded = await expand_template_with_ai(template, contact)
            subject = expanded["subject"]
            body = expanded["body"]
            
            # Create draft - it only becomes "sent" after a real SMTP delivery
            draft = Draft(
                contact_id=contact.id,
                subject=subject,
                body=body,
                status="draft",
                tenant_id=getattr(contact, "tenant_id", None),
            )
            self.db.add(draft)
            self.db.commit()
            self.db.refresh(draft)

            if auto_approve and send_via_smtp:
                smtp_config = get_smtp_for_tenant(
                    self.db, getattr(contact, "tenant_id", None)
                )
                try:
                    from app.services.tracking import send_html_for_draft

                    alias_name, alias_email = default_alias(
                        self.db, getattr(contact, "tenant_id", None), draft
                    )

                    send_email(
                        smtp_config,
                        contact.email,
                        subject,
                        body,
                        alias_name or None,
                        alias_email or None,
                        html_body=send_html_for_draft(
                            self.db, draft, getattr(contact, "tenant_id", None)
                        ),
                    )
                    draft.status = "sent"
                    draft.sent_at = datetime.now(timezone.utc)
                except MailNotConfigured as exc:
                    draft.status = "blocked"
                    draft.error_message = str(exc)
                except MailDeliveryError as exc:
                    draft.status = "failed"
                    draft.error_message = str(exc)
                self.db.commit()

            # Log
            log = Log(
                message=f"Draft created for {contact.email} from template {template.name}",
                level="info",
                tenant_id=getattr(contact, "tenant_id", None),
            )
            self.db.add(log)
            self.db.commit()

            return {
                "success": True,
                "draft_id": draft.id,
                "subject": subject,
                "body": body,
                "sent": draft.status == "sent"
            }
        
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
        
        finally:
            self.db.close()


@instrument_agent
class QueueManager:
    """Manages the email orchestration queue."""
    
    def __init__(self):
        self._alive = False
        self._last_poll = None
    
    @property
    def alive(self) -> bool:
        return self._alive
    
    @property
    def last_poll(self) -> Optional[float]:
        return self._last_poll
    
    async def process_queue(self, tenant_id: Optional[int] = None) -> Dict[str, Any]:
        """Send queued drafts through SMTP.

        Drafts are skipped (never marked sent) when SMTP is unconfigured or the
        recipient is not eligible. Only a message accepted by the relay sets
        ``status="sent"``.

        When ``tenant_id`` is given, only that tenant's drafts and SMTP config
        are touched. Background jobs pass one tenant at a time so a queue pass
        can never send another tenant's mail.
        """
        self._last_poll = datetime.now(timezone.utc).timestamp()
        db = SessionLocal()

        try:
            # Blocked drafts are retried: the block was often a fixable state
            # (recipient not yet approved, SMTP not configured) and eligibility
            # is re-checked below before anything is sent.
            draft_query = db.query(Draft).filter(
                Draft.status.in_(["draft", "blocked"])
            )
            if tenant_id is not None:
                draft_query = draft_query.filter(Draft.tenant_id == tenant_id)
            drafts = draft_query.order_by(Draft.id.asc()).limit(10).all()
            results = {"processed": 0, "sent": 0, "failed": 0, "skipped": 0, "details": []}

            if not drafts:
                self._alive = True
                return results

            smtp_config = get_smtp_for_tenant(db, tenant_id)
            if not is_configured(smtp_config):
                results["skipped"] = len(drafts)
                results["details"].append(
                    {"status": "skipped", "reason": "Mail transport is not configured"}
                )
                self._alive = True
                return results

            for draft in drafts:
                draft_tenant = tenant_id if tenant_id is not None else draft.tenant_id
                contact_query = db.query(Contact).filter(Contact.id == draft.contact_id)
                if draft_tenant is not None:
                    contact_query = contact_query.filter(
                        Contact.tenant_id == draft_tenant
                    )
                contact = contact_query.first()

                if not contact or not contact.email or not contact.eligible_to_email:
                    results["skipped"] += 1
                    results["details"].append(
                        {
                            "draft_id": draft.id,
                            "status": "skipped",
                            "reason": "recipient is not eligible to email",
                        }
                    )
                    continue

                if contact.email_blacklisted:
                    results["skipped"] += 1
                    results["details"].append(
                        {
                            "draft_id": draft.id,
                            "status": "skipped",
                            "reason": "recipient is blacklisted after a bounce",
                        }
                    )
                    continue

                # A placeholder row left in a contact list would bounce, but the
                # relay accepts it, so "sent" would be recorded for mail that
                # never arrived. Fail the draft instead: it must not be retried
                # and the contact must never be mailed again.
                problem = blocked_reason(contact.email, sender_address(smtp_config))
                if problem:
                    draft.status = "failed"
                    draft.error_message = problem
                    contact.eligible_to_email = False
                    contact.email_blacklisted = True
                    db.add(
                        Log(
                            message=(
                                f"Refused to email {contact.email}: {problem}"
                            ),
                            level="warning",
                            tenant_id=draft_tenant,
                        )
                    )
                    db.commit()
                    results["failed"] += 1
                    results["details"].append(
                        {
                            "draft_id": draft.id,
                            "status": "failed",
                            "reason": problem,
                        }
                    )
                    continue


                allowed, reason = check_send_allowed(db, contact)
                if not allowed:
                    if reason.startswith("Pacing"):
                        # Leave the remaining drafts queued for the next pass;
                        # do not pretend they were reviewed and skipped.
                        results["details"].append({"status": "paused", "reason": reason})
                        break
                    results["skipped"] += 1
                    results["details"].append(
                        {"draft_id": draft.id, "status": "skipped", "reason": reason}
                    )
                    continue

                claimed = (
                    db.query(Draft)
                    .filter(
                        Draft.id == draft.id,
                        Draft.status.in_(["draft", "blocked"]),
                    )
                )
                if draft_tenant is not None:
                    claimed = claimed.filter(Draft.tenant_id == draft_tenant)
                claimed = claimed.update(
                    {Draft.status: "sending"},
                    synchronize_session=False,
                )
                db.commit()
                if not claimed:
                    results["skipped"] += 1
                    results["details"].append(
                        {
                            "draft_id": draft.id,
                            "status": "skipped",
                            "reason": "draft changed before it could be sent",
                        }
                    )
                    continue

                draft.status = "sending"
                draft.attempt_count = (draft.attempt_count or 0) + 1
                db.commit()

                try:
                    # smtplib blocks; keep the event loop responsive.
                    from app.services.tracking import send_html_for_draft

                    alias_name, alias_email = default_alias(db, draft_tenant, draft)

                    await asyncio.to_thread(
                        send_email,
                        smtp_config,
                        contact.email,
                        draft.subject,
                        draft.body,
                        alias_name or None,
                        alias_email or None,
                        send_html_for_draft(db, draft, draft_tenant),
                    )
                except MailDeliveryError as exc:
                    draft.status = "failed"
                    draft.error_message = str(exc)
                    if (draft.variables or {}).get("message_kind") == "auto_reply":
                        db.add(
                            Event(
                                tenant_id=draft_tenant,
                                contact_id=draft.contact_id,
                                event_type="auto_reply_failed",
                                data={
                                    "reply_event_id": (draft.variables or {}).get("reply_event_id"),
                                    "message": str(exc),
                                    "subject": draft.subject,
                                },
                            )
                        )
                    db.commit()
                    results["failed"] += 1
                    results["details"].append(
                        {"draft_id": draft.id, "status": "failed", "error": str(exc)}
                    )
                else:
                    draft.status = "sent"
                    draft.sent_at = datetime.now(timezone.utc)
                    draft.error_message = None
                    record_usage(db, draft_tenant, EMAILS_SENT)
                    if (draft.variables or {}).get("message_kind") == "auto_reply":
                        db.add(
                            Event(
                                tenant_id=draft_tenant,
                                contact_id=draft.contact_id,
                                event_type="auto_reply_sent",
                                data={
                                    "reply_event_id": (draft.variables or {}).get("reply_event_id"),
                                    "message": "Automatic reply sent",
                                    "subject": draft.subject,
                                },
                            )
                        )
                    db.commit()
                    results["sent"] += 1
                    results["details"].append(
                        {"draft_id": draft.id, "status": "sent", "recipient": contact.email}
                    )

                results["processed"] += 1

            self._alive = True
            return results

        except Exception as e:
            logger.error("Queue processing failed: %s", e)
            return {"processed": 0, "error": str(e)}

        finally:
            db.close()


@dataclass
class ReplyClassification:
    """Result of classifying an email reply."""
    reply_type: str  # positive_response, negative_response, question, spam, no_reply_needed
    confidence: float  # 0.0 to 1.0
    sentiment: str  # positive, neutral, negative
    key_points: List[str]  # Extracted key points from the reply
    suggested_action: str  # next_action: follow_up, schedule_call, no_action, etc.
    needs_human_review: bool  # Whether to flag for human review


@instrument_agent
class ReplyAnalyzerAgent:
    """Analyzes incoming email replies and classifies them."""
    
    REPLY_TYPE_PROMPTS = {
        "positive_response": "The recipient is interested and willing to engage further",
        "negative_response": "The recipient is not interested or declining",
        "question": "The recipient has questions or is asking for more information",
        "spam": "Unsolicited or irrelevant content",
        "no_reply_needed": "Acknowledgment with no need for follow-up"
    }
    
    SENTIMENT_PROMPTS = {
        "positive": "The message expresses interest, enthusiasm, or willingness",
        "neutral": "The message is factual, neutral, or simply acknowledges",
        "negative": "The message expresses disinterest, frustration, or rejection"
    }
    
    def __init__(self, contact_id: Optional[int] = None, draft_id: Optional[int] = None):
        """Initialize the reply analyzer agent.
        
        Args:
            contact_id: Optional contact ID the reply is from
            draft_id: Optional draft ID this reply may be responding to
        """
        self.contact_id = contact_id
        self.draft_id = draft_id
        self.db = SessionLocal()
    
    def classify_reply(self, subject: str, body: str, sender_email: str) -> ReplyClassification:
        """Classify an incoming email reply.
        
        Args:
            subject: The email subject line
            body: The email body content
            sender_email: The sender email address
            
        Returns:
            ReplyClassification object with classification results
        """
        try:
            # Try AI classification if NVIDIA API key is configured
            llm = get_llm_client()
            if llm:
                return self._classify_with_ai(llm, subject, body, sender_email)
        except Exception as e:
            logger.warning(f"AI classification failed: {e}")
        
        # Fallback to rule-based classification
        return self._classify_rule_based(subject, body, sender_email)
    
    def _classify_with_ai(self, llm, subject: str, body: str, sender_email: str) -> ReplyClassification:
        """Classify using NVIDIA LLM."""
        messages = [
            SystemMessage(
                content="""You are an email reply classifier. Analyze the incoming reply and classify it.
Return your response as a valid JSON object with the following structure:
{
  "reply_type": "one of: positive_response, negative_response, question, spam, no_reply_needed",
  "confidence": 0.0-1.0,
  "sentiment": "positive, neutral, or negative",
  "key_points": ["list of main points from the reply"],
  "suggested_action": "one of: follow_up, schedule_call, no_action, send_questionnaire, etc.",
  "needs_human_review": true or false
}"""
            ),
            HumanMessage(
                content=f"""Subject: {subject}
From: {sender_email}
Body: {body}

Classify this email reply."""
            ),
        ]

        result = llm.invoke(messages)
        response_text = result.content if hasattr(result, 'content') else str(result)
        
        # Parse JSON response
        try:
            data = json.loads(response_text)
            return ReplyClassification(
                reply_type=data.get("reply_type", "no_reply_needed"),
                confidence=float(data.get("confidence", 0.5)),
                sentiment=data.get("sentiment", "neutral"),
                key_points=data.get("key_points", []),
                suggested_action=data.get("suggested_action", "follow_up"),
                needs_human_review=bool(data.get("needs_human_review", False))
            )
        except json.JSONDecodeError:
            # Fallback if AI response is not valid JSON
            return self._classify_rule_based(subject, body, sender_email)
    
    def _classify_rule_based(self, subject: str, body: str, sender_email: str) -> ReplyClassification:
        """Classify using rule-based logic (fallback when AI is unavailable)."""
        body_lower = body.lower()
        subject_lower = subject.lower()
        
        # Detect spam indicators
        spam_keywords = ["viagra", "casino", "lottery", "winner", "click here", "unsubscribe"]
        is_spam = any(kw in body_lower for kw in spam_keywords)
        
        if is_spam:
            return ReplyClassification(
                reply_type="spam",
                confidence=0.9,
                sentiment="neutral",
                key_points=["Spam content detected"],
                suggested_action="no_action",
                needs_human_review=True
            )
        
        # Detect positive responses
        positive_indicators = [
            "interested", "would like", "let's", "sounds great", "looking forward",
            "yes", "agreed", "definitely", "count me in", "much appreciated",
            "helpful", "excellent", "perfect", "great timing"
        ]
        
        # Detect thank you patterns - more nuanced
        thanks_positive = ["thanks for", "very helpful", "much appreciated", "thank you again"]
        
        # Detect negative responses - explicit declining patterns
        negative_indicators = [
            "not interested", "no thanks", "can't", "unable to", "not working",
            "decline", "decided against", "too expensive", "not a fit", "busy",
            "not the right time", "unavailable", "not interested at this time"
        ]
        
        # Detect strong negative patterns (higher priority)
        strong_negative_patterns = [
            "not interested", "no thank you", "not the right fit", "not a good fit",
            "can't move forward", "unable to pursue", "too expensive for us",
            "not the right time", "not interested at this time"
        ]
        
        # Detect questions
        question_indicators = ["?", "how", "what", "when", "where", "can you", "please explain"]
        
        # Count matches
        positive_matches = sum(1 for kw in positive_indicators if kw in body_lower)
        negative_matches = sum(1 for kw in negative_indicators if kw in body_lower)
        question_matches = sum(1 for kw in question_indicators if kw in body_lower)
        strong_negative = any(kw in body_lower for kw in strong_negative_patterns)
        
        # Count thank you usage
        thanks_pattern_matches = sum(1 for kw in thanks_positive if kw in body_lower)
        if "thanks" in body_lower or "thank you" in body_lower:
            if thanks_pattern_matches > 0:
                positive_matches += 1
        
        # Determine reply type - strong negative takes priority
        if strong_negative or (negative_matches > positive_matches and negative_matches > 0):
            reply_type = "negative_response"
            confidence = min(0.95, max(negative_matches, 2) * 0.25)
            sentiment = "negative"
        elif question_matches > 0:
            reply_type = "question"
            confidence = min(0.8, question_matches * 0.2)
            sentiment = "neutral"
        elif positive_matches > negative_matches:
            reply_type = "positive_response"
            confidence = min(0.9, positive_matches * 0.2)
            sentiment = "positive"
        else:
            reply_type = "no_reply_needed"
            confidence = 0.6
            sentiment = "neutral"
        
        # Extract key points (simple heuristic)
        key_points = []
        if any(kw in body_lower for kw in ["meeting", "call", "schedule", "availability"]):
            key_points.append("Meeting availability mentioned")
        if any(kw in body_lower for kw in ["price", "cost", "fee", "budget"]):
            key_points.append("Pricing discussion mentioned")
        if any(kw in body_lower for kw in ["question", "help", "support", "explain"]):
            key_points.append("Questions or support request")
        
        # Determine suggested action
        if reply_type == "positive_response":
            suggested_action = "schedule_call"
            needs_human_review = False
        elif reply_type == "question":
            suggested_action = "follow_up"
            needs_human_review = False
        elif reply_type == "negative_response":
            suggested_action = "no_action"
            needs_human_review = False
        else:
            suggested_action = "no_action"
            needs_human_review = False
        
        return ReplyClassification(
            reply_type=reply_type,
            confidence=confidence,
            sentiment=sentiment,
            key_points=key_points,
            suggested_action=suggested_action,
            needs_human_review=needs_human_review
        )
    
    def analyze_reply(
        self,
        subject: str,
        body: str,
        sender_email: str,
        record_usage_metric: bool = True,
    ) -> Dict[str, Any]:
        """Full analysis workflow including database logging.
        
        Args:
            subject: Email subject
            body: Email body
            sender_email: Sender email address
            record_usage_metric: Whether to meter this reply. The inbox pipeline
                passes ``False`` because it records ``replies_received`` itself
                after de-duplicating the message; recording here as well counted
                every reply twice.
            
        Returns:
            Dictionary with classification results
        """
        classification = self.classify_reply(subject, body, sender_email)
        
        # Find related contact if available
        contact = None
        event_id = None
        try:
            if self.contact_id:
                contact = self.db.query(Contact).filter(Contact.id == self.contact_id).first()
            elif sender_email:
                contact = self.db.query(Contact).filter(Contact.email == sender_email).first()
            
            # Create event record
            reply_tenant = getattr(contact, "tenant_id", None)
            event = Event(
                tenant_id=reply_tenant,
                contact_id=contact.id if contact else None,
                event_type="reply_received",
                data={
                    "subject": subject,
                    "body_preview": body[:500] if body else "",
                    "sender_email": sender_email,
                    "classification": {
                        "reply_type": classification.reply_type,
                        "confidence": classification.confidence,
                        "sentiment": classification.sentiment,
                        "key_points": classification.key_points,
                        "suggested_action": classification.suggested_action,
                        "needs_human_review": classification.needs_human_review
                    }
                }
            )
            self.db.add(event)
            if record_usage_metric:
                record_usage(self.db, reply_tenant, REPLIES_RECEIVED)
            
            # Log the event
            log = Log(message=f"Reply classified as {classification.reply_type} (confidence: {classification.confidence}) from {sender_email}", level="info", tenant_id=reply_tenant)
            self.db.add(log)
            self.db.commit()
            
            if contact:
                self.db.refresh(event)
                event_id = event.id
        except Exception as e:
            # If database operations fail, still return the classification
            logger.warning(f"Database logging failed: {e}")
        
        return {
            "reply_type": classification.reply_type,
            "confidence": classification.confidence,
            "sentiment": classification.sentiment,
            "key_points": classification.key_points,
            "suggested_action": classification.suggested_action,
            "needs_human_review": classification.needs_human_review,
            "contact_id": contact.id if contact else None,
            "event_id": event_id
        }
    
    def close(self):
        """Close database connection."""
        self.db.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ============================================================================
# PERSONALIZED EMAIL AGENT
# ============================================================================

def get_settings_for_tenant(db, tenant_id: Optional[int]):
    """Return the settings row for ``tenant_id``.

    Falls back to the first row only when no tenant is given, which keeps the
    single-tenant background jobs working while never mixing tenant settings.
    """
    query = db.query(Settings)
    if tenant_id is not None:
        query = query.filter(Settings.tenant_id == tenant_id)
    return query.order_by(Settings.id.asc()).first()


def get_smtp_for_tenant(db, tenant_id: Optional[int]):
    """Return the mailbox to send from for ``tenant_id``.

    Resolution (stored row, then the local deployment's environment) lives in
    ``app.services.mailer`` so every send path agrees on which mailbox is used.
    """
    from app.services.mailer import resolve_smtp_config

    return resolve_smtp_config(db, tenant_id)


@instrument_agent
class PersonalizedEmailAgent:
    """Generates personalized email content for specific contacts.
    
    This agent takes a draft template and contact information to produce
    a fully personalized email ready for sending.
    """
    
    def __init__(self, contact_id: int, template_id: int | None = None, draft_id: int | None = None):
        """Initialize the personalized email agent.
        
        Args:
            contact_id: ID of the contact to personalize for
            template_id: Optional template ID to use
            draft_id: Optional draft ID to personalize
        """
        self.contact_id = contact_id
        self.template_id = template_id
        self.draft_id = draft_id
        self.db = SessionLocal()
    
    def _get_contact_context(self, contact: Contact) -> Dict[str, Any]:
        """Build context dictionary from contact information."""
        settings_row = get_settings_for_tenant(
            self.db, getattr(contact, "tenant_id", None)
        )
        settings = {
            "goal": settings_row.goal if settings_row else "",
            "business_name": settings_row.business_name if settings_row else "",
            "business_offer": settings_row.business_offer if settings_row else "",
            "footer_text": settings_row.footer_text if settings_row else "",
            "sender_name": settings_row.sender_name if settings_row else "",
            "sender_role": settings_row.sender_role if settings_row else "",
            "company_website": settings_row.company_website if settings_row else "",
        }
        
        return {
            "company": contact.company or "",
            "first_name": (contact.name or "").split()[0] if contact.name else "",
            "last_name": " ".join((contact.name or "").split()[1:]) if contact.name and len((contact.name or "").split()) > 1 else "",
            "role": contact.role or "",
            "industry": contact.industry or "",
            "goal": settings.get("goal", ""),
            "business_name": settings.get("business_name", ""),
            "business_offer": settings.get("business_offer", ""),
            "footer_text": settings.get("footer_text", ""),
            "sender_name": settings.get("sender_name", ""),
            "sender_role": settings.get("sender_role", ""),
            "company_website": settings.get("company_website", ""),
            "calendly_url": settings_row.calendly_url if settings_row else "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "contact_email": contact.email,
        }
    
    def personalize(
        self, 
        subject_template: str | None = None,
        body_template: str | None = None,
        use_ai: bool = True,
        max_tokens: int = 1000
    ) -> Dict[str, str]:
        """Generate personalized email content.
        
        Args:
            subject_template: Subject line template (Jinja2 supported)
            body_template: Email body template (Jinja2 supported)
            use_ai: Whether to use AI for personalization
            max_tokens: Maximum tokens for AI response
            
        Returns:
            Dictionary with 'subject' and 'body' keys
        """
        contact = self.db.query(Contact).filter(Contact.id == self.contact_id).first()
        if not contact:
            raise ValueError(f"Contact {self.contact_id} not found")
        
        if not contact.eligible_to_email:
            raise ValueError(f"Contact {self.contact_id} is not eligible for email")
        
        # Get templates from database if not provided
        if subject_template is None or body_template is None:
            if self.template_id:
                template = self.db.query(Template).filter(Template.id == self.template_id).first()
                if template:
                    subject_template = subject_template or template.subject_template
                    body_template = body_template or template.body_template
            elif self.draft_id:
                draft = self.db.query(Draft).filter(Draft.id == self.draft_id).first()
                if draft:
                    subject_template = subject_template or draft.subject
                    body_template = body_template or draft.body
        
        if not subject_template or not body_template:
            raise ValueError("Subject and body templates are required")
        
        variables = self._get_contact_context(contact)
        
        # Try AI personalization first if enabled
        if use_ai:
            llm = get_llm_client()
            if llm:
                try:
                    result = self._personalize_with_ai(
                        llm, subject_template, body_template, variables
                    )
                    if result:
                        return result
                except Exception as e:
                    logger.warning(f"AI personalization failed: {e}")
        
        # Fallback to template expansion
        return {
            "subject": expand_template_variables(subject_template, variables),
            "body": expand_template_variables(body_template, variables)
        }
    
    def _personalize_with_ai(
        self, 
        llm, 
        subject_template: str, 
        body_template: str, 
        variables: Dict[str, Any]
    ) -> Dict[str, str] | None:
        """Use AI to personalize email content."""
        messages = [
            SystemMessage(
                content=(
                    "You are an expert email copywriter. Your task is to personalize and "
                    "enhance email content while maintaining a professional tone. "
                    "Keep the subject concise and the body compelling."
                )
            ),
            HumanMessage(
                content=f"""Subject Template: {subject_template}
Body Template: {body_template}

Contact Variables:
{json.dumps(variables, indent=2)}

Please produce a personalized subject line and body. 
Reply with ONLY a JSON object in this exact format:
{{"subject": "personalized subject", "body": "personalized body"}}

Make it sound natural and engaging, referencing the specific contact details provided.
"""
            )
        ]
        
        # ``llm.invoke`` is a blocking call and this method is reached from async
        # endpoints, so it must not be wrapped in ``asyncio.run`` (which raises
        # "event loop is already running" and silently fell back to templates).
        result = llm.invoke(messages)
        content = result.content if hasattr(result, "content") else str(result)
        
        # Parse JSON response
        text = str(content).strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        
        try:
            data = json.loads(text)
            if data.get("subject") and data.get("body"):
                from app.services.mailer import sanitize_subject

                return {"subject": sanitize_subject(data["subject"]), "body": data["body"]}
        except json.JSONDecodeError:
            pass
        
        return None
    
    def close(self):
        """Close database connection."""
        self.db.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ============================================================================
# SENDER AGENT
# ============================================================================

@instrument_agent
class SenderAgent:
    """Handles email delivery through SMTP with proper error handling.
    
    This agent manages the low-level details of SMTP delivery including
    authentication, connection management, and error recovery.
    """
    
    def __init__(self, smtp_config: Optional[SMTPConfig] = None):
        """Initialize sender agent with optional SMTP configuration."""
        from app.services.mailer import SMTPConfigView

        self.smtp_config = smtp_config or SMTPConfigView()
        self._connection = None
    
    def is_configured(self) -> bool:
        """Check if SMTP is properly configured."""
        return is_configured(self.smtp_config)
    
    def validate_configuration(self) -> Tuple[bool, str]:
        """Validate SMTP configuration.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        from app.services.mailer import active_transport

        if active_transport() == "gmail_api":
            return (
                (True, "")
                if self.is_configured()
                else (False, "Gmail API OAuth is not configured")
            )
        if not self.smtp_config.host:
            return False, "SMTP host not configured"
        if not self.smtp_config.user:
            return False, "SMTP user not configured"
        if not self.smtp_config.password:
            return False, "SMTP password not configured"
        if not isinstance(self.smtp_config.port, int):
            return False, "SMTP port must be an integer"
        if not 1 <= self.smtp_config.port <= 65535:
            return False, "SMTP port must be between 1 and 65535"
        return True, ""
    
    def test_connection(self, timeout: int = 10) -> Tuple[bool, str]:
        """Test the configured transport and, when credentials exist, auth.

        When the active transport is Resend the app sends through its REST API
        over HTTPS, which is the only path that works on hosts blocking SMTP
        ports (Render free tier). That path is tested here instead of the SMTP
        socket probe, which would time out on such hosts and report a false
        negative.
        """
        from app.services.mailer import active_transport

        if active_transport() == "gmail_api":
            if not self.is_configured():
                return False, "Gmail API is not configured for this workspace"
            from app.services.google_mail import test_connection

            result = test_connection()
            return bool(result.get("ok")), str(result.get("message") or "")
        if active_transport() == "resend":
            return self._test_resend()

        from app.services.mailer import test_connection

        host = (getattr(self.smtp_config, "host", "") or "").strip()
        if not host:
            return False, "SMTP host not configured"

        result = test_connection(
            host,
            getattr(self.smtp_config, "port", 587),
            (getattr(self.smtp_config, "user", "") or "").strip() or None,
            getattr(self.smtp_config, "password", "") or None,
        )
        ok = bool(result.get("ok")) and result.get("authenticated", True) is not False
        return ok, str(result.get("message") or "")

    def _test_resend(self) -> Tuple[bool, str]:
        """Verify the Resend API key by sending a 1-byte test message.

        Resend charges for real sends, so the test posts a message with a
        clearly fake recipient and reports whatever the API says: a 200 with
        an id means the key works (the recipient rejection is expected), while
        a 401 means the key is invalid.
        """
        import httpx

        from app.config import settings as app_settings
        from app.services.mailer import RESEND_API_URL, RESEND_TIMEOUT_SECONDS

        sender = (
            getattr(self.smtp_config, "sender", None)
            or app_settings.RESEND_FROM
            or app_settings.DEFAULT_SMTP_SENDER
            or app_settings.DEFAULT_SMTP_USER
            or "test@example.com"
        )
        payload = {
            "from": sender,
            "to": "test@resend.dev",
            "subject": "Connection test",
            "text": "Email Orchestrator connection test",
        }
        try:
            with httpx.Client(timeout=RESEND_TIMEOUT_SECONDS) as client:
                resp = client.post(
                    RESEND_API_URL,
                    headers={
                        "Authorization": f"Bearer {app_settings.RESEND_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            return False, f"Resend API unreachable: {exc}"

        if resp.status_code == 401:
            return False, "Resend API key rejected (401)"
        if resp.status_code == 403:
            return False, "Resend API key forbidden (403) - check domain verification"
        if resp.status_code >= 400:
            try:
                detail = resp.json()
                message = detail.get("message") or resp.text
            except Exception:
                message = resp.text or f"HTTP {resp.status_code}"
            return False, f"Resend rejected test send: {message}"
        return True, "Resend API connection successful"
    
    def send(
        self,
        to_email: str,
        subject: str,
        body: str,
        from_name: Optional[str] = None,
        from_email: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """Send an email via SMTP.
        
        Args:
            to_email: Recipient email address
            subject: Email subject line
            body: Email body (plain text)
            from_name: Optional sender name override
            from_email: Optional sender email override
            
        Returns:
            Tuple of (success, message, message_id)
        """
        from app.services.mailer import send_email
        
        if not from_email:
            from app.services.mailer import sender_address

            from_email = sender_address(self.smtp_config) or self.smtp_config.user
        
        if not from_name:
            from_name = "Email Orchestrator"
        
        try:
            message_id = send_email(
                self.smtp_config,
                to_email,
                subject,
                body,
                from_name=from_name,
                from_email=from_email
            )
            return True, "Email sent successfully", message_id
        except MailNotConfigured as e:
            return False, f"SMTP not configured: {e}", None
        except MailDeliveryError as e:
            return False, f"Delivery failed: {e}", None
        except Exception as e:
            return False, f"Unexpected error: {e}", None
    
    async def send_async(
        self,
        to_email: str,
        subject: str,
        body: str,
        from_name: Optional[str] = None,
        from_email: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """Send an email asynchronously."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.send,
            to_email,
            subject,
            body,
            from_name,
            from_email
        )
    
    def close(self):
        """Clean up resources."""
        if self._connection:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None


# ============================================================================
# CALENDAR AGENT
# ============================================================================

@instrument_agent
class CalendarAgent:
    """Provide a configured Calendly booking link without claiming event creation."""
    
    def __init__(
        self,
        provider: str = "manual",
        api_key: Optional[str] = None,
        booking_url: Optional[str] = None,
    ):
        """Initialize calendar agent.
        
        Args:
            provider: Calendar provider. Only a configured Calendly link is supported.
            api_key: Reserved for future provider integrations.
        """
        self.provider = provider.lower()
        self.api_key = api_key
        self.booking_url = (booking_url or "").strip()
    
    def list_calendars(self) -> List[Dict[str, Any]]:
        """List the configured Calendly booking page, if available."""
        if self.provider == "calendly":
            return (
                [{"id": "calendly-link", "name": "Calendly booking page", "url": self.booking_url}]
                if self.available()
                else []
            )
        
        return []
    
    def create_event(
        self,
        summary: str,
        start_time: datetime,
        duration_minutes: int = 30,
        attendees: Optional[List[str]] = None,
        description: Optional[str] = None,
        location: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fail explicitly because bookings are created by invitees through Calendly."""
        if self.provider == "calendly":
            raise ValueError(
                "Calendly events are created when invitees book through the configured booking link."
            )
        raise ValueError(
            f"Calendar event creation is not configured for provider '{self.provider}'."
        )
    
    def generate_meeting_link(self, meeting_type: str = "call") -> str:
        """Generate a meeting link for the configured provider.
        
        Args:
            meeting_type: Type of meeting (call, meeting, demo)
            
        Returns:
            Meeting URL
        """
        return self.booking_url if self.available() else ""
    
    def available(self) -> bool:
        """Check if calendar integration is available."""
        parsed = urlparse(self.booking_url)
        hostname = (parsed.hostname or "").lower()
        return (
            self.provider == "calendly"
            and parsed.scheme == "https"
            and (hostname == "calendly.com" or hostname.endswith(".calendly.com"))
        )


# ============================================================================
# AI BRAIN AGENT
# ============================================================================

@instrument_agent
class AIBrainAgent:
    """AI-powered intelligence layer for email enhancement.
    
    Provides:
    - Subject line optimization
    - Content personalization
    - Tone adjustment
    - Content summarization
    - A/B test variant generation
    """
    
    def __init__(self, model_name: Optional[str] = None):
        """Initialize AI brain agent."""
        from app.config import settings as app_settings

        self.model_name = model_name or app_settings.NVIDIA_MODEL
        self._llm = None
        self._initialized = False
    
    def _ensure_initialized(self):
        """Lazily initialize the LLM client."""
        if not self._initialized:
            self._llm = get_llm_client()
            self._initialized = True
    
    def enhance_subject(self, subject: str, context: Optional[Dict] = None) -> str:
        """Optimize email subject line.
        
        Args:
            subject: Original subject line
            context: Additional context (contact, goal, etc.)
            
        Returns:
            Optimized subject line
        """
        self._ensure_initialized()
        
        if not self._llm:
            # Fallback: capitalize first letter, limit length
            return subject[0].upper() + subject[1:] if subject else subject
        
        prompt = f"Optimize this email subject line to be more engaging and concise (max 10 words):\n\n'{subject}'"
        if context:
            prompt += f"\n\nContext: {json.dumps(context)}"
        
        try:
            result = self._llm.invoke([HumanMessage(content=prompt)])
            # A model answers with prose, quotes or markdown; a Subject header
            # must be one clean line or the message cannot be built.
            from app.services.mailer import sanitize_subject

            return sanitize_subject(str(result.content if hasattr(result, 'content') else result))
        except Exception as e:
            logger.warning(f"Subject optimization failed: {e}")
            return subject
    
    def enhance_body(self, body: str, style: str = "professional") -> str:
        """Enhance email body content.
        
        Args:
            body: Original email body
            style: Tone style (professional, friendly, casual)
            
        Returns:
            Enhanced body text
        """
        self._ensure_initialized()
        
        if not self._llm:
            return body
        
        prompt = f"""Rewrite this email body to be more {style}, clearer, and more persuasive.
Keep the same key message but improve the wording.

Body:
{body[:500]}

Return only the enhanced body text."""
        
        try:
            result = self._llm.invoke([HumanMessage(content=prompt)])
            content = str(result.content if hasattr(result, 'content') else result)
            # Remove any markdown formatting if present
            if content.startswith("```"):
                content = content.strip("`").strip()
            return content
        except Exception as e:
            logger.warning(f"Body enhancement failed: {e}")
            return body
    
    def generate_alternatives(
        self,
        subject: str,
        body: str,
        count: int = 3
    ) -> List[Dict[str, str]]:
        """Generate A/B test alternatives.
        
        Args:
            subject: Original subject
            body: Original body
            count: Number of alternatives to generate
            
        Returns:
            List of alternatives with 'subject' and 'body' keys
        """
        self._ensure_initialized()
        
        if not self._llm:
            return [{"subject": subject, "body": body} for _ in range(count)]
        
        prompt = f"""Generate {count} alternative versions of this email.
Each should have a different subject line and slightly varied body.

Original:
Subject: {subject}
Body: {body[:300]}...

Return as JSON array:
{{"alternatives": [{{"subject": "...", "body": "..."}}, ...]]}}"""
        
        alternatives = []
        try:
            result = self._llm.invoke([HumanMessage(content=prompt)])
            content = str(result.content if hasattr(result, 'content') else result)
            
            if content.startswith("```"):
                content = content.strip("`")
                if content.lower().startswith("json"):
                    content = content[4:]
            
            data = json.loads(content.strip())
            alternatives = data.get("alternatives", [])
        except Exception as e:
            logger.warning(f"Alternative generation failed: {e}")
        
        # Ensure we return at least the originals
        while len(alternatives) < count:
            alternatives.append({"subject": subject, "body": body})
        
        return alternatives
    
    def summarize_thread(self, messages: List[str]) -> str:
        """Summarize email thread or conversation.
        
        Args:
            messages: List of message bodies
            
        Returns:
            Summary text
        """
        self._ensure_initialized()
        
        if not self._llm:
            return " ".join(messages[:3]) if messages else ""
        
        combined = "\n\n".join(messages[-5:])  # Last 5 messages
        prompt = f"Summarize this email thread in 2-3 sentences:\n\n{combined}"
        
        try:
            result = self._llm.invoke([HumanMessage(content=prompt)])
            return str(result.content if hasattr(result, 'content') else result)
        except Exception as e:
            logger.warning(f"Thread summarization failed: {e}")
            return ""
    
    def extract_action_items(self, email_text: str) -> List[str]:
        """Extract action items from email content.
        
        Args:
            email_text: Email body to analyze
            
        Returns:
            List of action items
        """
        self._ensure_initialized()
        
        prompt = f"""Extract action items or tasks from this email.
Return as a simple list, one per line.

Email:
{email_text[:500]}"""
        
        if not self._llm:
            return []
        
        try:
            result = self._llm.invoke([HumanMessage(content=prompt)])
            content = str(result.content if hasattr(result, 'content') else result)
            return [line.strip() for line in content.strip().split("\n") if line.strip()]
        except Exception as e:
            logger.warning(f"Action item extraction failed: {e}")
            return []


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def create_agent_for_task(task_type: str, **kwargs) -> Any:
    """Factory function to create appropriate agent for a task.
    
    Args:
        task_type: Type of agent needed
        
    Returns:
        Agent instance
    """
    agents = {
        "personalize": PersonalizedEmailAgent,
        "send": SenderAgent,
        "calendar": CalendarAgent,
        "brain": AIBrainAgent,
        "reply_analyze": ReplyAnalyzerAgent,
        "reply": ReplyAnalyzerAgent,
    }
    
    if task_type not in agents:
        raise ValueError(f"Unknown agent type: {task_type}")
    
    return agents[task_type](**kwargs)


# ============================================================================
# AUTO-RESPONSE WORKFLOW
# ============================================================================

@instrument_agent
class AutoResponder:
    """Handles automatic replies to classified email responses.
    
    This agent takes a classified reply and generates an appropriate
    response based on the reply type and contact information.
    """
    
    RESPONSE_TEMPLATES = {
        "positive_response": {
            "subject_prefix": "Re:",
            "body": """Welcome, {{ first_name }}!

Thank you for your interest in {{ sender_company }}. I'm glad you're considering working with us.

I'd be happy to discuss how we can help with {{ business_offer }}.

{% if calendar_link %}Choose a time that works for you: {{ calendar_link }}{% else %}Reply with a convenient time and we will coordinate.{% endif %}

Looking forward to connecting!

Best regards,
{{ sender_name }}
{{ sender_title }}
{{ sender_company }}"""
        },
        "question": {
            "subject_prefix": "Re:",
            "body": """Hi {{ first_name }},

Thanks for your question! I'd be happy to provide more details about our services.

At {{ sender_company }}, we help businesses with {{ business_offer }}.

I can share specific growth ideas tailored for your company. Would you like to schedule a brief call to discuss?

{% if calendar_link %}Choose a time here: {{ calendar_link }}{% endif %}

Looking forward to helping you out!

Best regards,
{{ sender_name }}
{{ sender_title }}
{{ sender_company }}"""
        },
        "schedule_call": {
            "subject_prefix": "Re:",
            "body": """Hi {{ first_name }},

Perfect! I'm looking forward to our call.

{% if calendar_link %}Choose a time that works for you: {{ calendar_link }}{% else %}Reply with a convenient time and we will coordinate.{% endif %}

I'll be ready to discuss how we can help {{ sender_company }} with {{ business_offer }}.

Looking forward to speaking with you.

Best regards,
{{ sender_name }}
{{ sender_title }}
{{ sender_company }}"""
        },
    }
    
    def __init__(self, contact_id: int, smtp_config=None, sender_agent=None):
        """Initialize auto-responder.
        
        Args:
            contact_id: ID of the contact to respond to
            smtp_config: SMTP configuration for sending
            sender_agent: Optional SenderAgent instance
        """
        from app.config import settings as app_settings
        
        self.db = SessionLocal()
        self.contact_id = contact_id
        self.smtp_config = smtp_config
        self.sender_agent = sender_agent
        contact_tenant_id = None
        if contact_id is not None:
            contact_row = (
                self.db.query(Contact).filter(Contact.id == contact_id).first()
            )
            if contact_row is not None:
                contact_tenant_id = contact_row.tenant_id
        self.settings = get_settings_for_tenant(self.db, contact_tenant_id)
        self.sender_name = (
            self.settings.sender_name if self.settings and self.settings.sender_name else "The Team"
        )
        self.sender_company = self.settings.business_name or "Your Company" if self.settings else "Your Company"
        self.sender_title = self.settings.sender_role if self.settings and self.settings.sender_role else "Team Member"
        self.calendar_agent = CalendarAgent(
            provider="calendly",
            booking_url=self.settings.calendly_url if self.settings else None,
        )
    
    def generate_response(
        self, 
        classification: Dict[str, Any],
        original_subject: str,
        original_body: str,
        sender_email: str
    ) -> Dict[str, Any]:
        """Generate an appropriate auto-response based on classification.
        
        Args:
            classification: Classification result from ReplyAnalyzerAgent
            original_subject: Original email subject
            original_body: Original email body
            sender_email: Original sender email
            
        Returns:
            Dictionary with response details or None if no response needed
        """
        reply_type = classification.get("reply_type", "no_reply_needed")
        
        if reply_type not in self.RESPONSE_TEMPLATES:
            return None
        
        contact = self.db.query(Contact).filter(Contact.id == self.contact_id).first()
        if not contact or not contact.eligible_to_email:
            return None

        template = self.RESPONSE_TEMPLATES[reply_type]

        # Generate subject
        subject = f"{template['subject_prefix']} {original_subject.replace('Re:', '').strip()}"

        # Generate body
        variables = {
            "first_name": (contact.name or "there").split()[0] if contact.name else "there",
            "sender_name": self.sender_name,
            "sender_title": self.sender_title,
            "sender_company": self.sender_company,
            "business_offer": self.settings.business_offer or "our services" if self.settings else "our services",
            "meeting_proposal": self._generate_meeting_proposal(),
            "question_topic": "your question",
            "additional_info": "I'd be happy to provide more details on our services. Let's discuss this during our call.",
            "availability_options": "Monday-Friday, 9am-5pm EST",
            "calendar_link": self._generate_calendar_link(),
            "subject": original_subject.replace("Re:", "").strip(),
        }

        # Prefer the tenant's editable reply template (category "reply") so the
        # dashboard can change the wording without a redeploy. Fall back to the
        # hardcoded body when no active reply template exists, which keeps the
        # auto-responder working on workspaces that never seeded one.
        from jinja2 import Template as JinjaTemplate

        db_template = (
            self.db.query(Template)
            .filter(
                Template.tenant_id == contact.tenant_id,
                Template.category == "reply",
                Template.is_active == True,  # noqa: E712 - SQLAlchemy boolean
            )
            .order_by(Template.id.asc())
            .first()
        )
        if db_template is not None and (db_template.body_template or "").strip():
            body = JinjaTemplate(db_template.body_template).render(**variables)
            if (db_template.subject_template or "").strip():
                subject = JinjaTemplate(db_template.subject_template).render(**variables)
        else:
            body = JinjaTemplate(template["body"]).render(**variables)

        return {
            "subject": subject,
            "body": body,
            "reply_type": reply_type,
            "reply_event_id": classification.get("event_id"),
            "to_email": sender_email,
            "from_name": self.sender_name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def _generate_meeting_proposal(self) -> str:
        """Generate meeting time proposal."""
        from datetime import datetime, timedelta
        
        today = datetime.now()
        # Find next Tuesday or Thursday
        days_ahead = (2 - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 2  # Tuesday
        meeting_day = today + timedelta(days=days_ahead)
        
        return f"{meeting_day.strftime('%A, %B %d at 10:00 AM EST')}"
    
    def _generate_calendar_link(self) -> str:
        """Return the configured Calendly booking URL, if available."""
        if self.calendar_agent and self.calendar_agent.available():
            return self.calendar_agent.generate_meeting_link("call")
        return ""
    
    def send_response(
        self, 
        response: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Queue the auto-response so standard sending limits are enforced."""
        if not response:
            return {"success": False, "message": "No response generated"}
        
        contact = self.db.query(Contact).filter(Contact.id == self.contact_id).first()
        if not contact or not contact.eligible_to_email:
            return {"success": False, "message": "Contact is not eligible for email"}
        if contact.email_blacklisted:
            return {"success": False, "message": "Contact is blacklisted after a bounce"}
        problem = blocked_reason(response.get("to_email") or contact.email)
        if problem:
            return {"success": False, "message": problem}

        try:
            self.db.add(
                Draft(
                    contact_id=self.contact_id,
                    tenant_id=contact.tenant_id,
                    subject=response["subject"],
                    body=response["body"],
                    status="draft",
                    variables={
                        "message_kind": "auto_reply",
                        "reply_event_id": response.get("reply_event_id"),
                    },
                )
            )
            self.db.commit()
            return {
                "success": True,
                "message": "Automatic reply queued",
                "response": {
                    "subject": response["subject"],
                    "body_preview": response["body"][:200],
                    "to_email": response["to_email"],
                },
            }
        except Exception as e:
            self.db.rollback()
            return {
                "success": False,
                "message": str(e),
                "response": response,
            }
    
    def log_interaction(
        self, 
        event_id: int,
        send_result: Dict[str, Any]
    ) -> None:
        """Log the auto-response interaction."""
        sent = bool(send_result.get("success"))
        status = "queued" if sent else "failed"
        contact = self.db.query(Contact).filter(Contact.id == self.contact_id).first()
        tenant_id = contact.tenant_id if contact else None
        event = Event(
            contact_id=self.contact_id,
            tenant_id=tenant_id,
            event_type=f"auto_reply_{status}",
            data={
                "reply_event_id": event_id,
                "message": send_result.get("message", "unknown"),
                "subject": (send_result.get("response") or {}).get("subject"),
            },
        )
        self.db.add(event)
        log = Log(
            message=f"Auto-response {status} for reply {event_id}: {send_result.get('message', 'unknown')}",
            level="info" if sent else "warning",
            tenant_id=tenant_id,
        )
        self.db.add(log)
        self.db.commit()
    
    def close(self):
        """Close database connection."""
        self.db.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()