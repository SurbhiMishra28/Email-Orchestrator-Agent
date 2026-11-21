"""Email verification service with syntax, MX, and SMTP checks."""
import re
import socket
import smtplib
import dns.resolver
import logging
from typing import Optional, Tuple, List
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Common disposable email domains (subset for performance)
DISPOSABLE_DOMAINS = {
    "10minutemail.com", "guerrillamail.com", "mailinator.com", "tempmail.com",
    "throwaway.email", "yopmail.com", "trashmail.com", "maildrop.cc",
    "getnada.com", "fakeinbox.com", "temp-mail.org", "dispostable.com",
    "spamgourmet.com", "mohmal.com", "emailondeck.com", "mintemail.com",
    "minutemailbox.com", "spambox.us", "tempemail.co", "jetable.org",
    "mailnesia.com", "spamavert.com", "trbvn.com", "yopmail.fr",
    "yopmail.net", "yopmail.gq", "yopmail.ml", "yopmail.ga",
}

# Common free email providers (for catch-all reference)
FREE_PROVIDERS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "yahoo.ca",
    "outlook.com", "hotmail.com", "live.com", "msn.com", "icloud.com",
    "me.com", "mac.com", "aol.com", "protonmail.com", "proton.me",
    "zoho.com", "yandex.com", "mail.ru", "gmx.com", "gmx.de",
}

# Email regex (RFC 5322 simplified but practical)
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)


@dataclass
class VerificationResult:
    """Result of email verification."""
    email: str
    status: str  # deliverable, undeliverable, risky, inconclusive
    smtp_check: str  # passed, failed, not_checked
    mx_check: str  # passed, failed, not_checked
    catch_all: bool
    disposable: bool
    domain: str
    error: Optional[str] = None


def validate_syntax(email: str) -> Tuple[bool, Optional[str]]:
    """Validate email syntax."""
    if not email or len(email) > 254:
        return False, "Email too long or empty"
    
    if not EMAIL_REGEX.match(email):
        return False, "Invalid email format"
    
    # Check for consecutive dots
    if ".." in email:
        return False, "Consecutive dots not allowed"
    
    # Check local part length
    local_part = email.split("@")[0]
    if len(local_part) > 64:
        return False, "Local part too long"
    
    return True, None


def extract_domain(email: str) -> str:
    """Extract domain from email."""
    return email.split("@")[-1].lower()


def check_mx_records(domain: str) -> Tuple[bool, List[str], Optional[str]]:
    """Check MX records for domain."""
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        mx_records = [str(r.exchange).rstrip('.') for r in answers]
        mx_records.sort(key=lambda x: [int(p) if p.isdigit() else p for p in x.split('.')])
        return True, mx_records, None
    except dns.resolver.NXDOMAIN:
        return False, [], "Domain does not exist"
    except dns.resolver.NoAnswer:
        return False, [], "No MX records found"
    except dns.resolver.Timeout:
        return False, [], "DNS timeout"
    except Exception as e:
        return False, [], f"DNS error: {str(e)}"


def check_smtp_deliverability(email: str, mx_records: List[str], timeout: int = 10) -> Tuple[bool, str, Optional[str]]:
    """Check a mailbox with RCPT TO.

    Returns ``(success, status, error)`` where status is one of:
    ``passed`` (mailbox accepted), ``failed`` (server explicitly rejected the
    mailbox) or ``unreachable`` (no server could be contacted).  Only an
    explicit rejection is proof that an address is bad; a blocked port or
    timeout must stay inconclusive.
    """
    if not mx_records:
        return False, "failed", "No MX records to test"

    domain = extract_domain(email)
    sender = f"verify@{domain}"  # Use same domain for sender
    last_error = None

    for mx in mx_records[:3]:  # Try top 3 MX records
        try:
            with smtplib.SMTP(mx, 25, timeout=timeout) as server:
                server.ehlo_or_helo_if_needed()
                server.mail(sender)
                code, message = server.rcpt(email)
                detail = message.decode() if isinstance(message, bytes) else message

                if code == 250:
                    return True, "passed", None
                if code in (550, 551, 552, 553):
                    return False, "failed", f"Rejected ({code}): {detail}"

                # 4xx responses are temporary; do not call the mailbox invalid.
                last_error = f"Temporary SMTP response {code}: {detail}"
                continue

        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected):
            last_error = f"Could not connect to {mx}"
            continue
        except (socket.timeout, ConnectionRefusedError, OSError):
            last_error = f"Could not reach {mx}"
            continue
        except Exception as e:
            logger.debug(f"SMTP check failed for {mx}: {e}")
            last_error = f"SMTP check failed for {mx}: {e}"
            continue

    return False, "unreachable", last_error or "All MX servers unreachable"


def detect_catch_all(domain: str, mx_records: List[str], timeout: int = 10) -> bool:
    """Detect if domain accepts all emails (catch-all)."""
    if not mx_records:
        return False
    
    test_email = f"catchalltest_{int(datetime.now().timestamp())}@{domain}"
    sender = f"verify@{domain}"
    
    for mx in mx_records[:2]:
        try:
            with smtplib.SMTP(mx, 25, timeout=timeout) as server:
                server.ehlo_or_helo_if_needed()
                server.mail(sender)
                code, _ = server.rcpt(test_email)
                if code == 250:
                    return True
        except Exception:
            continue
    return False


def is_disposable(domain: str) -> bool:
    """Check if domain is a known disposable email provider."""
    return domain.lower() in DISPOSABLE_DOMAINS


def is_free_provider(domain: str) -> bool:
    """Check if domain is a known free email provider."""
    return domain.lower() in FREE_PROVIDERS


def verify_email(email: str, check_smtp: bool = True, check_catch_all: bool = True) -> VerificationResult:
    """
    Perform full email verification.
    
    Args:
        email: Email address to verify
        check_smtp: Whether to perform SMTP RCPT TO check
        check_catch_all: Whether to detect catch-all domains
    
    Returns:
        VerificationResult with all check results
    """
    domain = extract_domain(email)
    
    # 1. Syntax check
    syntax_ok, syntax_error = validate_syntax(email)
    if not syntax_ok:
        return VerificationResult(
            email=email,
            status="undeliverable",
            smtp_check="not_checked",
            mx_check="failed",
            catch_all=False,
            disposable=is_disposable(domain),
            domain=domain,
            error=syntax_error
        )
    
    # 2. MX record check
    mx_ok, mx_records, mx_error = check_mx_records(domain)
    mx_check_status = "passed" if mx_ok else "failed"
    
    if not mx_ok:
        definitive_mx_failure = mx_error in {
            "Domain does not exist",
            "No MX records found",
        }
        return VerificationResult(
            email=email,
            status="undeliverable" if definitive_mx_failure else "inconclusive",
            smtp_check="not_checked",
            mx_check=mx_check_status if definitive_mx_failure else "unreachable",
            catch_all=False,
            disposable=is_disposable(domain),
            domain=domain,
            error=mx_error
        )
    
    # 3. Disposable check
    disposable = is_disposable(domain)
    
    # 4. Catch-all detection
    catch_all = False
    if check_catch_all:
        catch_all = detect_catch_all(domain, mx_records)
    
    # 5. SMTP check
    smtp_check_status = "not_checked"
    smtp_error = None
    
    if check_smtp:
        smtp_ok, smtp_check_status, smtp_error = check_smtp_deliverability(email, mx_records)
    else:
        smtp_check_status = "not_checked"

    # Determine final status. Only explicit rejections are undeliverable;
    # an unreachable server means we simply do not know.
    if disposable:
        status = "risky"
    elif not mx_ok:
        status = "undeliverable"
    elif smtp_check_status == "passed":
        status = "risky" if catch_all else "deliverable"
    elif smtp_check_status == "failed":
        status = "undeliverable"
    else:
        status = "inconclusive"
    
    return VerificationResult(
        email=email,
        status=status,
        smtp_check=smtp_check_status,
        mx_check=mx_check_status,
        catch_all=catch_all,
        disposable=disposable,
        domain=domain,
        error=smtp_error
    )


def verify_bulk(emails: List[str], check_smtp: bool = True, check_catch_all: bool = True, 
                progress_callback=None) -> List[VerificationResult]:
    """
    Verify multiple emails with optional progress callback.
    
    Args:
        emails: List of email addresses
        check_smtp: Whether to perform SMTP checks
        check_catch_all: Whether to detect catch-all domains
        progress_callback: Optional function(current, total, result) called after each email
    
    Returns:
        List of VerificationResult
    """
    results = []
    total = len(emails)
    
    for i, email in enumerate(emails):
        result = verify_email(email, check_smtp, check_catch_all)
        results.append(result)
        
        if progress_callback:
            progress_callback(i + 1, total, result)
    
    return results