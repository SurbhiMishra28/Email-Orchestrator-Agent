"""Recognise delivery-failure notifications in the synced inbox.

The pipeline is unattended, so a bounce is the only signal that an address is
dead. Without this, a hard bounce is indistinguishable from a reply that never
came: the contact stays eligible, stays queued, and every follow-up bounces
again. Recognising the DSN lets the caller blacklist the recipient for good.

Detection is deliberately conservative. Only the standard bounce senders plus a
known DSN marker count, because a prospect writing "your message wasn't
delivered to my colleague" must not be mistaken for a bounce.
"""
import re
from email.utils import parseaddr
from typing import Optional, Set

# Senders a mail system uses for non-delivery reports. A human prospect does
# not write from these addresses.
BOUNCE_SENDERS = {
    "mailer-daemon",
    "postmaster",
    "mail-daemon",
    "mailerdaemon",
    "bounce",
    "bounces",
}

# Domains that are themselves mail systems when paired with a daemon local part.
BOUNCE_SENDER_DOMAINS = ("googlemail.com", "google.com")

# Phrases that appear in a real DSN. Matching any two (or one strong marker)
# keeps ordinary complaints from being treated as a bounce.
STRONG_MARKERS = (
    "delivery status notification",
    "address not found",
    "wasn't delivered to",
    "was not delivered to",
    "undelivered mail returned to sender",
    "returned mail: see transcript for details",
    "mail delivery failed",
    "delivery has failed",
    "recipient address rejected",
)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def is_bounce_sender(sender: str) -> bool:
    """True when the message comes from a mail-system bounce address."""
    local, _, domain = parseaddr(sender or "")[1].strip().lower().rpartition("@")
    if not local:
        return False
    if local in BOUNCE_SENDERS:
        return True
    return local == "mailer-daemon" and domain in BOUNCE_SENDER_DOMAINS


def looks_like_bounce(subject: str, body: str, sender: str = "") -> bool:
    """True for a message that is a delivery-failure notification."""
    text = f"{subject or ''}\n{body or ''}".lower()
    marker = any(phrase in text for phrase in STRONG_MARKERS)
    if not marker:
        return False
    # A marker alone is enough from a daemon; from anyone else the subject must
    # also read like a bounce report.
    if is_bounce_sender(sender):
        return True
    subject_text = (subject or "").lower()
    return "delivery status notification" in subject_text or "undelivered" in subject_text


def failed_recipients(subject: str, body: str, sender_email: str = "") -> Set[str]:
    """Addresses a DSN says could not be reached.

    The recipient is normally named inline ("Your message wasn't delivered to
    someone@example.com") or in a ``Final-Recipient`` part. Both are scanned and
    the bounce sender's own address is excluded.
    """
    text = f"{subject or ''}\n{body or ''}"
    candidates = {match.lower() for match in EMAIL_RE.findall(text)}

    # "Final-Recipient: rfc822; someone@example.com" is the machine-readable
    # form; it identifies the failed mailbox unambiguously.
    final = re.findall(
        r"final-recipient:\s*(?:rfc822;\s*)?([^\s<>;,]+@[^\s<>;,]+)",
        text,
        flags=re.IGNORECASE,
    )
    candidates.update(item.strip().strip(".").lower() for item in final)

    excluded = {sender_email.strip().lower()} if sender_email else set()
    return {address for address in candidates if address and address not in excluded}
