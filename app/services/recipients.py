"""Recipient sanity checks shared by every send path.

Real outreach must never leave the building for an address that cannot exist.
The pipeline is fully automatic, so a placeholder row left in a contact list
would otherwise be mailed, bounce, and (because a bounce is not a delivery
failure the SMTP relay reports) still be recorded as "sent".

Two kinds of address are refused here:

* reserved / documentation domains that can never receive mail
  (``example.com``, ``*.test``, ``localhost`` and the rest of RFC 2606 and
  RFC 6761), plus the conventional fake-mail hosts, and
* system mailboxes that must never be used as a prospect
  (``mailer-daemon@``, ``postmaster@``, bounce handlers).

The check is deliberately narrow: it only rejects what is provably not a real
recipient, so a legitimate small-business address is never filtered out.
"""
from typing import Optional

from ..config import settings

# RFC 2606 / RFC 6761 reserved names: they are guaranteed never to be routed.
RESERVED_DOMAINS = {
    "example.com",
    "example.net",
    "example.org",
    "example.edu",
    "test",
    "test.com",
    "invalid",
    "localhost",
    "local",
    "localdomain",
    "in-addr.arpa",
    "ip6.arpa",
}

# TLDs reserved for documentation/testing, matched as a suffix.
RESERVED_SUFFIXES = (".test", ".example", ".invalid", ".localhost", ".localdomain")

# Disposable inbox providers are real but are not prospects worth mailing.
DISPOSABLE_DOMAINS = {
    "getnada.com",
    "fakeinbox.com",
    "temp-mail.org",
    "tempmail.com",
    "dispostable.com",
    "mailinator.com",
    "guerrillamail.com",
    "10minutemail.com",
    "yopmail.com",
    "trashmail.com",
}

# Local-parts that belong to mail infrastructure, never to a human lead.
SYSTEM_LOCAL_PARTS = {
    "mailer-daemon",
    "postmaster",
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "bounce",
    "bounces",
    "abuse",
}


def domain_of(email: str) -> str:
    """The lowercased domain of an address ("" when it has none)."""
    local, _, domain = (email or "").strip().lower().rpartition("@")
    return domain if local else ""


def is_reserved_domain(domain: str) -> bool:
    """True for a domain that is guaranteed not to be a real mailbox host."""
    domain = (domain or "").strip().lower().rstrip(".")
    if not domain:
        return True
    if domain in RESERVED_DOMAINS:
        return True
    return any(domain.endswith(suffix) for suffix in RESERVED_SUFFIXES)


def address_problem(email: str, sender_email: Optional[str] = None) -> Optional[str]:
    """Return why ``email`` must not be mailed, or ``None`` when it may be.

    ``sender_email`` lets a caller also refuse the tenant's own address, which
    would otherwise be a self-send.
    """
    address = (email or "").strip().lower()
    if not address:
        return "recipient address is empty"
    if "@" not in address:
        return "recipient address is not an email address"

    local, _, domain = address.rpartition("@")
    if not local or not domain:
        return "recipient address is not an email address"

    if is_reserved_domain(domain):
        return f"recipient domain {domain} is reserved for examples/tests and cannot receive mail"
    if domain in DISPOSABLE_DOMAINS:
        return f"recipient domain {domain} is a disposable mailbox provider"
    if local in SYSTEM_LOCAL_PARTS:
        return f"recipient {local}@ is a mail system mailbox, not a contact"

    if sender_email and address == (sender_email or "").strip().lower():
        return "recipient is the sender's own address"

    return None


def is_mailable(email: str, sender_email: Optional[str] = None) -> bool:
    """Convenience wrapper: ``True`` when the address passes every check."""
    return address_problem(email, sender_email) is None


def guard_enabled() -> bool:
    """Whether the send paths must enforce the recipient checks.

    Tests intentionally use reserved example.com addresses, so they turn this
    off; every real deployment leaves it on.
    """
    return bool(settings.BLOCK_PLACEHOLDER_RECIPIENTS)


def blocked_reason(email: str, sender_email: Optional[str] = None) -> Optional[str]:
    """Why ``email`` must not be mailed, honouring the deployment flag.

    Returns ``None`` both for a good address and when the guard is disabled, so
    callers can treat a non-``None`` result as "refuse this send".
    """
    if not guard_enabled():
        return None
    return address_problem(email, sender_email)
